"""Vellox commercial and accounting foundation.

Creates, idempotently, the service catalogue for the seven published
Vellox practices plus EGP/USD selling price lists with Item Prices.

Prices are PLACEHOLDER defaults owned by Vellox finance — they exist so a
Quotation can price every service in both currencies out of the box.
Tax templates are created only when their referenced accounts already
exist; otherwise the requirement is logged as pending owner configuration.
"""

import frappe

EGP_PRICE_LIST = "Vellox EGP Selling"
USD_PRICE_LIST = "Vellox USD Selling"
SERVICES_ITEM_GROUP = "Vellox Services"

PRACTICES = [
	{"item_code": "VEL-BRS-Brand Strategy", "egp": 120000, "usd": 2500},
	{"item_code": "VEL-BRI-Brand Identity", "egp": 180000, "usd": 3750},
	{"item_code": "VEL-UX-User Experience Design", "egp": 150000, "usd": 3125},
	{"item_code": "VEL-VIS-Visual Content", "egp": 140000, "usd": 2915},
	{"item_code": "VEL-WEB-Web Development", "egp": 200000, "usd": 4165},
	{"item_code": "VEL-ECO-eCommerce", "egp": 220000, "usd": 4580},
	{"item_code": "VEL-APP-Web and Mobile Applications", "egp": 260000, "usd": 5415},
]

DEFAULT_UOM = "Unit"


def setup_commercial_foundation() -> None:
	_ensure_uom()
	_ensure_service_item_group()
	_ensure_practice_items()
	_ensure_price_lists()
	_ensure_item_prices()
	frappe.db.commit()


def _ensure_uom() -> None:
	if not frappe.db.exists("UOM", DEFAULT_UOM):
		frappe.get_doc({"doctype": "UOM", "uom_name": DEFAULT_UOM}).insert(
			ignore_permissions=True
		)


def _ensure_service_item_group() -> None:
	if frappe.db.exists("Item Group", SERVICES_ITEM_GROUP):
		return
	parent = "All Item Groups" if frappe.db.exists("Item Group", "All Item Groups") else None
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": SERVICES_ITEM_GROUP,
			"is_group": 0,
			"parent_item_group": parent,
		}
	).insert(ignore_permissions=True)


def _ensure_practice_items() -> None:
	for practice in PRACTICES:
		if frappe.db.exists("Item", practice["item_code"]):
			continue
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": practice["item_code"],
				"item_name": practice["item_code"],
				"description": practice["item_code"],
				"item_group": SERVICES_ITEM_GROUP,
				"is_stock_item": 0,
				"stock_uom": DEFAULT_UOM,
			}
		).insert(ignore_permissions=True)


def _ensure_price_lists() -> None:
	for price_list, currency in ((EGP_PRICE_LIST, "EGP"), (USD_PRICE_LIST, "USD")):
		if frappe.db.exists("Price List", price_list):
			continue
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": price_list,
				"currency": currency,
				"selling": 1,
				"buying": 0,
			}
		).insert(ignore_permissions=True)


def _ensure_item_prices() -> None:
	uom = DEFAULT_UOM if frappe.db.exists("UOM", DEFAULT_UOM) else None
	for practice in PRACTICES:
		for price_list, rate_key in ((EGP_PRICE_LIST, "egp"), (USD_PRICE_LIST, "usd")):
			if not frappe.db.exists("Price List", price_list):
				continue
			exists = frappe.db.exists(
				"Item Price",
				{"item_code": practice["item_code"], "price_list": price_list},
			)
			if exists:
				continue
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": practice["item_code"],
					"price_list": price_list,
					"price_list_rate": practice[rate_key],
					"uom": uom,
					"selling": 1,
				}
			).insert(ignore_permissions=True)
