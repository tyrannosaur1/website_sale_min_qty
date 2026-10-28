# -*- coding: utf-8 -*-
"""The two pages a customer actually touches.

The product page is fetched over HTTP and parsed, because an attribute that is
set on the wrong element (or on the template instead of the variant) looks
perfectly fine in the source and does nothing in the browser.
"""
from lxml import html as lxml_html

from odoo.tests.common import HttpCase


class ShopPageCase(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.min_qty_message = False
        cls.product = cls.env["product.template"].create({
            "name": "Bulk Nuts",
            "type": "consu",
            "sale_ok": True,
            "list_price": 10.0,
            "min_order_qty": 2,
            "qty_step": 0.25,
            "website_published": True,
        })

    def _quantity_input(self, page):
        nodes = lxml_html.fromstring(page).xpath("//input[@name='add_qty']")
        self.assertEqual(len(nodes), 1, "the quantity input must be rendered once")
        return nodes[0]

    def test_the_product_page_carries_the_grid_and_the_sentence(self):
        response = self.url_open(self.product.website_url)
        self.assertEqual(response.status_code, 200)
        node = self._quantity_input(response.text)
        self.assertEqual(node.get("step"), "0.25")
        self.assertEqual(float(node.get("data-min")), 2.0)
        self.assertEqual(float(node.get("value")), 2.0)
        self.assertIn("multiples of 0.25", response.text)
        self.assertIn("Minimum order: 2", response.text)

    def test_the_website_sentence_replaces_the_default_one(self):
        self.website.min_qty_message = "Sold in quarters of a kilo, minimum {min}."
        response = self.url_open(self.product.website_url)
        self.assertIn("Sold in quarters of a kilo, minimum 2.", response.text)
        self.assertNotIn("Minimum order: 2", response.text)

    def test_a_product_without_rules_says_nothing(self):
        """Negative control on the page: no note, no step, no minimum."""
        plain = self.env["product.template"].create({
            "name": "Loose Nuts", "type": "consu", "sale_ok": True,
            "list_price": 10.0, "website_published": True,
        })
        response = self.url_open(plain.website_url)
        self.assertEqual(response.status_code, 200)
        node = self._quantity_input(response.text)
        self.assertEqual(node.get("step"), "1.0")
        self.assertEqual(float(node.get("data-min")), 1.0)
        self.assertNotIn("o_ws_min_qty_note", response.text)

    def _cart_for_a_portal_customer(self, quantity):
        user = self.env["res.users"].create({
            "name": "Portal Shopper",
            "login": "min_qty_shopper",
            "password": "min_qty_shopper",
            "groups_id": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.env["sale.order"].create({
            "partner_id": user.partner_id.id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {
                "product_id": self.product.product_variant_id.id,
                "product_uom_qty": quantity,
            })],
        })
        self.authenticate("min_qty_shopper", "min_qty_shopper")

    def test_checkout_waits_while_a_line_is_below_the_minimum(self):
        self._cart_for_a_portal_customer(1)
        response = self.url_open("/shop/checkout", allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/shop/cart", response.headers.get("Location", ""))

    def test_checkout_goes_on_when_the_cart_is_valid(self):
        self._cart_for_a_portal_customer(2)
        response = self.url_open("/shop/checkout", allow_redirects=False)
        self.assertNotIn("/shop/cart", response.headers.get("Location", ""))
