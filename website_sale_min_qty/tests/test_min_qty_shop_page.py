# -*- coding: utf-8 -*-
"""The pages a customer actually touches.

The product page is fetched over HTTP and parsed, because an attribute that is
set on the wrong element (or on the template instead of the variant) looks
perfectly fine in the source and does nothing in the browser. The checkout
guard is called the way the payment route calls it.
"""
from lxml import html as lxml_html

from odoo.exceptions import ValidationError
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

    # ------------------------------------------------------------------
    # The checkout guard, called where the payment page calls it
    # ------------------------------------------------------------------
    def _cart(self, quantity):
        partner = self.env["res.partner"].create({"name": "Portal Shopper"})
        return self.env["sale.order"].create({
            "partner_id": partner.id,
            "website_id": self.website.id,
            "order_line": [(0, 0, {
                "product_id": self.product.product_variant_id.id,
                "product_uom_qty": quantity,
            })],
        })

    def test_checkout_is_refused_while_a_line_is_below_the_minimum(self):
        order = self._cart(1)
        with self.assertRaises(ValidationError) as caught:
            order._check_cart_is_ready_to_be_paid()
        self.assertIn("Bulk Nuts", str(caught.exception))
        self.assertIn("at least 2", str(caught.exception))

    def test_checkout_is_not_refused_by_this_module_when_the_cart_is_valid(self):
        """Positive control: the guard stays quiet on a cart that obeys the rule.

        The core check that follows may still refuse the cart for its own
        reasons (no delivery method here), so the assertion is on *this*
        module's message rather than on the exception.
        """
        order = self._cart(2)
        try:
            order._check_cart_is_ready_to_be_paid()
        except ValidationError as error:
            self.assertNotIn("Bulk Nuts", str(error))
