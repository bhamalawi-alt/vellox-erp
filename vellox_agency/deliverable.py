"""Vellox Deliverable lifecycle engine.

transition(doc, action) moves a deliverable by named action; validate enforces
the same status order on every save, so the form and the API follow it too
([P3-146]). The docstatus column stays 0 (non-submittable); track_changes
captures the audit trail.
"""

import frappe
from frappe import _

LEGAL_TRANSITIONS = {
    "Draft": {
        "submit_for_review": "Internal Review",
        "cancel": "Cancelled",
    },
    "Internal Review": {
        "internal_approve": "Client Review",
        "request_changes": "Changes Requested",
        "cancel": "Cancelled",
    },
    "Client Review": {
        "client_approve": "Approved",
        "request_changes": "Changes Requested",
        "cancel": "Cancelled",
    },
    "Changes Requested": {
        "submit_for_review": "Internal Review",
        "cancel": "Cancelled",
    },
}
# Approved and Cancelled are terminal — no outgoing transitions.
ALLOWED_MOVES = {status: set(actions.values()) for status, actions in LEGAL_TRANSITIONS.items()}

# Delivery plan sections 5 and 8: sending work to the client, recording the
# client's answer, approving and changing the revision allowance are for these.
DELIVERY_MANAGER_ROLES = ("System Manager", "Agency Manager", "Vellox Project Manager")
MANAGER_ONLY_STATUSES = {"Client Review", "Approved"}
DEFAULT_REVISION_ALLOWANCE = 2
ROUND_FIELDS = ("reviewer", "audience", "outcome", "comments", "reviewed_on")


def _is_delivery_manager() -> bool:
    return bool(set(DELIVERY_MANAGER_ROLES) & set(frappe.get_roles()))


def _require_delivery_manager(what: str) -> None:
    if not _is_delivery_manager():
        frappe.throw(
            _("Only a Project Manager or the Agency Manager can {0}.").format(what), frappe.PermissionError
        )

REQUIRE_CLIENT_REVIEW_FOR_APPROVE = True


def transition(doc, action):
    """Move doc to the next status via the named action.

    Raises frappe.ValidationError on illegal transitions or unmet preconditions.
    Updates doc.status in place; caller must call doc.save() afterwards.
    """
    if _is_revision_exhausted(doc) and action == "submit_for_review":
        doc.status = "Changes Requested"
        frappe.throw(
            _("Revision allowance ({0}) exhausted. A Change Request is required "
              "before further review rounds.").format(doc.revision_allowance),
            frappe.ValidationError,
        )
    current = doc.status
    rule = LEGAL_TRANSITIONS.get(current, {})
    target = rule.get(action)
    if not target:
        frappe.throw(
            _("Illegal transition {0} → action '{1}'.").format(
                frappe.bold(current), frappe.bold(action)
            ),
            frappe.ValidationError,
        )

    if action == "client_approve" and REQUIRE_CLIENT_REVIEW_FOR_APPROVE:
        _require_approved_client_round(doc)

    # Emails are sent by the Notification records in delivery_setup when the
    # caller saves the new status.
    doc.status = target

    if target == "Approved":
        doc.accepted_on = frappe.utils.now_datetime()
        doc.accepted_by = frappe.session.user

    _sync_current_version(doc)


def validate_deliverable(doc, method=None):
    """Hook: enforce the status order, who may do what, and the append-only history on every save."""
    before = None if doc.is_new() else doc.get_doc_before_save()
    if before:
        _enforce_version_immutability(doc)
    _enforce_review_rounds(doc, before)
    _enforce_allowance(doc, before)
    _enforce_status_move(doc)
    # Notification conditions cannot count child rows, so the exhausted check
    # reaches the "Revision Allowance Exhausted" condition as a per-save flag.
    # Set here, not in transition(), because users also change status on the form.
    doc.flags.revision_exhausted = doc.status == "Changes Requested" and _is_revision_exhausted(doc)
    # Notifications can only address fields on the record itself ([P3-99]).
    # Falls back to the creator, who received this alert before [P3-99].
    doc.project_manager = frappe.db.get_value("Project", doc.project, "custom_vellox_project_manager") or doc.owner


def _enforce_status_move(doc):
    """Allow only the moves transition() allows, whoever saves the deliverable."""
    before = None if doc.is_new() else doc.get_doc_before_save()
    new = doc.status or "Draft"
    # Who approved and when change only on the save that approves.
    doc.accepted_by = before.accepted_by if before else None
    doc.accepted_on = before.accepted_on if before else None
    if not before:
        if new != "Draft":
            frappe.throw(_("A new deliverable starts as a Draft."), frappe.ValidationError)
        return
    old = before.status or "Draft"
    if old == new:
        return
    if new not in ALLOWED_MOVES.get(old, set()):
        frappe.throw(
            _("A deliverable cannot move from {0} to {1}.").format(frappe.bold(old), frappe.bold(new)),
            frappe.ValidationError,
        )
    if new in MANAGER_ONLY_STATUSES:
        _require_delivery_manager(_("move a deliverable to {0}").format(frappe.bold(new)))
    if old == "Changes Requested" and new == "Internal Review" and _is_revision_exhausted(doc):
        frappe.throw(
            _("Revision allowance ({0}) exhausted. A Change Request is required, then a manager "
              "can raise the allowance for further review rounds.").format(doc.revision_allowance),
            frappe.ValidationError,
        )
    if old == "Client Review" and new == "Changes Requested":
        _require_latest_client_round(doc, "Changes Requested")
    if new == "Approved":
        _require_approved_client_round(doc)
        # Always the real approver and time: these fields are read-only on the
        # form, but a client can still send values for them.
        doc.accepted_on = frappe.utils.now_datetime()
        doc.accepted_by = frappe.session.user
    _sync_current_version(doc)


def _enforce_review_rounds(doc, before):
    """Review rounds are the approval record: append-only, and client answers come from managers."""
    old_rounds = {r.name: r for r in (before.review_rounds if before else []) if r.name}
    current = {r.name for r in doc.review_rounds or [] if r.name}
    if set(old_rounds) - current:
        frappe.throw(_("Review rounds cannot be removed."), frappe.ValidationError)
    for row in doc.review_rounds or []:
        old = old_rounds.get(row.name)
        if old:
            if any(str(row.get(f) or "") != str(old.get(f) or "") for f in ROUND_FIELDS):
                frappe.throw(_("Review rounds cannot be changed after they are added."), frappe.ValidationError)
        elif row.audience == "Client":
            _require_delivery_manager(_("record the client's answer"))


def _enforce_allowance(doc, before):
    """Raising the allowance reopens review rounds, so only managers may; lowering is stricter."""
    previous = before.revision_allowance if before else DEFAULT_REVISION_ALLOWANCE
    if (doc.revision_allowance or 0) > (previous or 0):
        _require_delivery_manager(_("raise the revision allowance"))


def _enforce_version_immutability(doc):
    """Existing version rows must not be modified after insert."""
    if not doc.get_doc_before_save():
        return
    old_versions = {
        v.name: v.as_dict()
        for v in (doc.get_doc_before_save().versions or [])
        if v.name
    }
    for row in doc.versions or []:
        if row.name and row.name in old_versions:
            old = old_versions[row.name]
            for field in ("version_number", "file_url", "notes"):
                if str(row.get(field)) != str(old.get(field)):
                    frappe.throw(
                        _("Version rows are immutable after creation. "
                          "Create a new version instead."),
                        frappe.ValidationError,
                    )


def _is_revision_exhausted(doc):
    """Return True if review rounds consumed > revision_allowance."""
    rounds_used = len(doc.review_rounds or [])
    allowance = doc.revision_allowance or 0
    return rounds_used > allowance


def _require_latest_client_round(doc, outcome):
    """The client's answer must be on record before work leaves Client Review."""
    rounds = doc.review_rounds or []
    latest = rounds[-1] if rounds else None
    if not latest or latest.audience != "Client" or latest.outcome != outcome:
        frappe.throw(
            _("Record the client review round (outcome '{0}') first.").format(outcome),
            frappe.ValidationError,
        )


def _require_approved_client_round(doc):
    """At least one Review Round with audience=Client, outcome=Approved must exist."""
    has_client_approval = any(
        r.audience == "Client" and r.outcome == "Approved"
        for r in (doc.review_rounds or [])
    )
    if not has_client_approval:
        frappe.throw(
            _("A client review round with outcome 'Approved' is required before final approval."),
            frappe.ValidationError,
        )


def _sync_current_version(doc):
    """Set current_version to the highest version_number in the versions table."""
    versions = doc.get("versions") or []
    if versions:
        max_version = max(v.version_number for v in versions)
        doc.current_version = max_version
