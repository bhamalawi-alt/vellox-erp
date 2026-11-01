app_name = "vellox_agency"
app_title = "Vellox Agency"
app_publisher = "Vellox Team"
app_description = "Open source ERP for media agencies"
app_email = "admin@velloxagency.com"
app_license = "mit"

# Apps
# ------------------

# Frappe HR holds staff, holidays and leave ([P4-102], capacity plan P4-29).
required_apps = ["erpnext", "hrms"]

before_migrate = "vellox_agency.compatibility.validate_runtime_compatibility"

# Vellox settings (sales stages, lost reasons, the lead assignment rule,
# notifications, roles) are kept by apply_baseline, not `fixtures` ([P3-100]).
# Fixtures re-import whole records on every migrate. The setup code instead
# creates what is missing and resets only the values it owns (stage
# probabilities, role desk access, the rule's users); notifications and other
# records an admin may edit are created once and then left alone.
after_migrate = "vellox_agency.security.apply_baseline"

doctype_js = {"Quotation": "public/js/quotation_offer_builder.js"}

# Block new use of duplicate custom ledgers; ERPNext records are authoritative.
doc_events = {
	doctype: {
		"before_insert": "vellox_agency.deprecations.guard_deprecated_doctype",
		"on_trash": "vellox_agency.deprecations.guard_deprecated_doctype",
	}
	for doctype in (
		"Client Account",
		"Agency Project",
		"Agency Timesheet",
		"Expense",
		"Agency Invoice",
		"Engagement",
		"Retainer",
	)
}

# Lead routing follows roles and Lead access; re-sync whenever either changes.
# after_delete (not on_trash) so the deleted row no longer counts.
for _doctype in ("User", "User Permission", "Custom DocPerm", "Role"):
	doc_events[_doctype] = {
		"on_update": "vellox_agency.crm_setup.sync_lead_assignment_users",
		"after_delete": "vellox_agency.crm_setup.sync_lead_assignment_users",
	}

# Role Permission Manager edits Lead permissions with direct DB writes that skip
# doc hooks, so lead routing is also re-synced every hour.
scheduler_events = {
	"hourly": [
		"vellox_agency.crm_setup.sync_lead_assignment_users",
		"vellox_agency.security.revoke_shares_beyond_jobs",
	],
	"daily": [
		"vellox_agency.lead_followup.send_late_reply_digest",
		"vellox_agency.scheduled.send_stale_opportunity_reminders",
		"vellox_agency.profit.refresh_project_profit",
	],
}

# Shares and assignments never give more than the receiver's job ([P3-140]).
doc_events["DocShare"] = {"validate": "vellox_agency.security.validate_share_within_job"}
doc_events["ToDo"] = {"validate": "vellox_agency.security.validate_todo_within_access"}

doc_events["Task"] = {
	"on_update": "vellox_agency.project_phase.sync_project_phase",
	"after_delete": "vellox_agency.project_phase.sync_project_phase",
}

# Customer billing figures: Finance and the Agency Manager only ([P3-142]).
doc_events["Customer"] = {"onload": "vellox_agency.security.hide_customer_money"}

# Timesheet rates come from Activity Cost for jobs that cannot see rates ([P4-31]).
doc_events["Timesheet"] = {"validate": "vellox_agency.rates.rederive_timesheet_rates"}

doc_events["Employee"] = {"validate": "vellox_agency.setup.people.validate_capacity_fields"}

doc_events["Lead"] = {
	"before_insert": "vellox_agency.crm_setup.stamp_first_response_due",
}

doc_events["Project"] = {
	# Runs before ERPNext's validate, which shares the project with new members.
	"before_insert": "vellox_agency.crm_setup.stamp_project_manager",
	"before_validate": "vellox_agency.security.remember_project_members",
	"validate": "vellox_agency.change_control.gate_health_transition",
	"on_update": "vellox_agency.security.forget_project_members",
}

doc_events["Vellox Change Request"] = {
	"validate": "vellox_agency.change_control.validate_change_request",
	"on_update": "vellox_agency.change_control.shift_schedule_on_approval",
}

doc_events["Deliverable"] = {
	"validate": "vellox_agency.deliverable.validate_deliverable",
}

doc_events["Quotation"] = {
	"validate": [
		"vellox_agency.estimate.apply_estimate_margin",
		"vellox_agency.approval.stamp_approval_on_validate",
	],
	"before_submit": "vellox_agency.approval.gate_submission",
	"onload": "vellox_agency.approval.add_quotation_actions",
}

doc_events["Opportunity"] = {
	"validate": [
		"vellox_agency.qualification_gate.require_qualified_lead",
		"vellox_agency.pipeline.require_lost_reason",
	],
	"before_validate": "vellox_agency.pipeline.apply_stage_probability",
	"before_save": "vellox_agency.pipeline.apply_stage_probability",
}

# Server-side permission enforcement (not UI decoration) for the same ledgers.
has_permission = {
	doctype: "vellox_agency.security.has_deprecated_doctype_access"
	for doctype in (
		"Client Account",
		"Agency Project",
		"Agency Timesheet",
		"Expense",
		"Agency Invoice",
		"Engagement",
		"Retainer",
	)
}

# Per-job access limits and team-member project scoping ([P3-140]). Must list
# security.GOVERNED_DOCTYPES plus "Deliverable" (checked by test_role_access).
JOB_ACCESS_DOCTYPES = (
	"Lead",
	"Opportunity",
	"Quotation",
	"Customer",
	"Contact",
	"Item",
	"Project",
	"Project Update",
	"Project Template",
	"Task",
	"Timesheet",
	"Activity Cost",
	"Sales Invoice",
	"Payment Entry",
	"Vellox Resource Allocation",
	"Sales Order",
	"Delivery Note",
	"POS Invoice",
	"POS Invoice Merge Log",
	"Account",
	"Cost Center",
	"Quality Action",
	"Quality Feedback",
	"Quality Goal",
	"Quality Meeting",
	"Quality Procedure",
	"Quality Review",
	"Deliverable",
)
for _doctype in JOB_ACCESS_DOCTYPES:
	has_permission[_doctype] = "vellox_agency.security.job_access_permission"

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "vellox_agency",
# 		"logo": "/assets/vellox_agency/logo.png",
# 		"title": "Vellox Agency",
# 		"route": "/vellox_agency",
# 		"has_permission": "vellox_agency.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/vellox_agency/css/vellox_agency.css"
# app_include_js = "/assets/vellox_agency/js/vellox_agency.js"

# include js, css files in header of web template
# web_include_css = "/assets/vellox_agency/css/vellox_agency.css"
# web_include_js = "/assets/vellox_agency/js/vellox_agency.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "vellox_agency/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "vellox_agency/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "vellox_agency.utils.jinja_methods",
# 	"filters": "vellox_agency.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "vellox_agency.install.before_install"
after_install = "vellox_agency.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "vellox_agency.uninstall.before_uninstall"
# after_uninstall = "vellox_agency.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "vellox_agency.utils.before_app_install"
# after_app_install = "vellox_agency.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "vellox_agency.utils.before_app_uninstall"
# after_app_uninstall = "vellox_agency.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "vellox_agency.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Comment": "vellox_agency.security.comment_permission_query",
}
for _doctype in JOB_ACCESS_DOCTYPES:
	permission_query_conditions[_doctype] = ["vellox_agency.security.job_access_query"]
permission_query_conditions["Deliverable"].insert(0, "vellox_agency.security.deliverable_permission_query")
permission_query_conditions["File"] = ["vellox_agency.security.job_access_file_query"]

# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"vellox_agency.tasks.all"
# 	],
# 	"daily": [
# 		"vellox_agency.tasks.daily"
# 	],
# 	"hourly": [
# 		"vellox_agency.tasks.hourly"
# 	],
# 	"weekly": [
# 		"vellox_agency.tasks.weekly"
# 	],
# 	"monthly": [
# 		"vellox_agency.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "vellox_agency.install.before_tests"

# Overriding Methods
# ------------------------------
#
# Exporting lists is limited by job ([P3-141]); see export_guard.
override_whitelisted_methods = {
	"frappe.desk.reportview.export_query": "vellox_agency.export_guard.export_query",
	"frappe.desk.query_report.export_query": "vellox_agency.export_guard.export_report",
	"frappe.core.doctype.data_export.exporter.export_data": "vellox_agency.export_guard.export_data",
	"frappe.core.doctype.data_import.data_import.download_template": "vellox_agency.export_guard.download_template",
	"frappe.utils.print_format.download_multi_pdf": "vellox_agency.export_guard.download_multi_pdf",
	"frappe.utils.print_format.download_multi_pdf_async": "vellox_agency.export_guard.download_multi_pdf_async",
	"frappe.contacts.doctype.contact.contact.download_vcards": "vellox_agency.export_guard.download_vcards",
	# Reports follow job access ([P3-147]); see report_guard.
	"frappe.desk.query_report.run": "vellox_agency.report_guard.run",
	"frappe.desk.query_report.get_script": "vellox_agency.report_guard.get_script",
	"frappe.core.doctype.prepared_report.prepared_report.make_prepared_report": "vellox_agency.report_guard.make_prepared_report",
	"frappe.desk.query_report.save_report": "vellox_agency.report_guard.save_report",
	# Rates follow job access ([P4-31]); see rates.
	"erpnext.projects.doctype.timesheet.timesheet.get_activity_cost": "vellox_agency.rates.get_activity_cost",
	"erpnext.projects.doctype.timesheet.timesheet.get_projectwise_timesheet_data": "vellox_agency.rates.get_projectwise_timesheet_data",
	"erpnext.projects.doctype.timesheet.timesheet.get_timesheet_data": "vellox_agency.rates.get_timesheet_data",
	"erpnext.projects.doctype.timesheet.timesheet.get_timesheet_detail_rate": "vellox_agency.rates.get_timesheet_detail_rate",
	"erpnext.projects.doctype.timesheet.timesheet.make_sales_invoice": "vellox_agency.rates.make_sales_invoice",
	# Write calls return only readable fields ([P4-31]); see client_guard.
	"frappe.client.set_value": "vellox_agency.client_guard.set_value",
	"frappe.client.insert": "vellox_agency.client_guard.insert",
	"frappe.client.save": "vellox_agency.client_guard.save",
	"frappe.client.submit": "vellox_agency.client_guard.submit",
	"frappe.client.cancel": "vellox_agency.client_guard.cancel",
	# Lists, counts and searches refuse filters on hidden fields ([P4-34]); see api_guard.
	"frappe.client.get_list": "vellox_agency.api_guard.get_list",
	"frappe.client.get_count": "vellox_agency.api_guard.get_count",
	"frappe.client.get_value": "vellox_agency.api_guard.get_value",
	"frappe.desk.reportview.get": "vellox_agency.api_guard.reportview_get",
	"frappe.desk.reportview.get_list": "vellox_agency.api_guard.reportview_get_list",
	"frappe.desk.reportview.get_count": "vellox_agency.api_guard.reportview_get_count",
	"frappe.desk.reportview.get_sidebar_stats": "vellox_agency.api_guard.get_sidebar_stats",
	"frappe.desk.listview.get_group_by_count": "vellox_agency.api_guard.get_group_by_count",
	"frappe.desk.search.search_link": "vellox_agency.api_guard.search_link",
	"frappe.desk.search.search_widget": "vellox_agency.api_guard.search_widget",
	"frappe.client.get": "vellox_agency.api_guard.get",
	"frappe.desk.reportview.get_stats": "vellox_agency.api_guard.get_stats",
	"frappe.desk.reportview.get_filter_dashboard_data": "vellox_agency.api_guard.get_filter_dashboard_data",
	"frappe.desk.form.utils.get_next": "vellox_agency.api_guard.get_next",
	"frappe.desk.calendar.get_events": "vellox_agency.api_guard.get_calendar_events",
	"erpnext.projects.doctype.timesheet.timesheet.get_events": "vellox_agency.api_guard.get_timesheet_events",
	"frappe.desk.doctype.number_card.number_card.get_result": "vellox_agency.api_guard.get_number_card_result",
	"frappe.desk.doctype.number_card.number_card.get_percentage_difference": "vellox_agency.api_guard.get_number_card_difference",
	"frappe.desk.doctype.dashboard_chart.dashboard_chart.get": "vellox_agency.api_guard.get_dashboard_chart",
	"frappe.client.validate_link": "vellox_agency.api_guard.validate_link",
	"frappe.geo.utils.get_coords": "vellox_agency.api_guard.get_coords",
	"frappe.utils.goal.get_monthly_goal_graph_data": "vellox_agency.api_guard.get_monthly_goal_graph_data",
	"frappe.www.list.get_list_data": "vellox_agency.api_guard.get_list_data",
	"erpnext.projects.utils.query_task": "vellox_agency.api_guard.query_task",
	"frappe.www.list.get": "vellox_agency.api_guard.get_portal_list",
	"frappe.desk.query_report.get_data_for_custom_field": "vellox_agency.api_guard.get_data_for_custom_field",
	# Document methods send the whole document back ([P4-34] review).
	"run_doc_method": "vellox_agency.api_guard.run_doc_method",
	"runserverobj": "vellox_agency.api_guard.run_doc_method",
	"frappe.handler.run_doc_method": "vellox_agency.api_guard.run_doc_method",
	"frappe.handler.runserverobj": "vellox_agency.api_guard.run_doc_method",
}

# REST lists refuse hidden filters; REST create and update return only readable fields ([P4-34]).
after_request = ["vellox_agency.api_guard.after_request"]

# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "vellox_agency.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "vellox_agency.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["vellox_agency.utils.before_request"]
# after_request = ["vellox_agency.utils.after_request"]

# Job Events
# ----------
# before_job = ["vellox_agency.utils.before_job"]
# after_job = ["vellox_agency.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"vellox_agency.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

