app_name = "vellox_agency"
app_title = "Vellox Agency"
app_publisher = "Vellox Team"
app_description = "Open source ERP for media agencies"
app_email = "admin@velloxagency.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

before_migrate = "vellox_agency.compatibility.validate_runtime_compatibility"

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

doc_events["Lead"] = {
	"before_insert": "vellox_agency.crm_setup.stamp_first_response_due",
}

doc_events["Quotation"] = {
	"validate": [
		"vellox_agency.estimate.apply_estimate_margin",
		"vellox_agency.approval.stamp_approval_on_validate",
	],
	"before_submit": "vellox_agency.approval.gate_submission",
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

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
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

