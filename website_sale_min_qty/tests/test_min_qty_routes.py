# -*- coding: utf-8 -*-
"""The routes, not just the model.

The model tests prove the arithmetic; they say nothing about whether a route
reaches it. Every route that can put a quantity in the cart is exercised here
against a product that carries an optional (``no_variant``) attribute, and the
quantity read back is the one PostgreSQL stores.

2.25 is deliberate: it is on a 0.25 grid but truncates to 2, which is also on
the grid, so only a comparison with the typed value can tell the two apart.
"""
import json

from lxml import html as lxml_html

from odoo.fields import Command
from odoo.tests.common import HttpCase


class CartRouteCase(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.attribute = cls.env["product.attribute"].create({
            "name": "Roast",
            "create_variant": "no_variant",
            "value_ids": [Command.create({"name": "Medium"})],
        })
        cls.product = cls.env["product.template"].create({
            "name": "Bulk Nuts",
            "type": "consu",
            "sale_ok": True,
            "list_price": 10.0,
            "qty_step": 0.25,
            "website_published": True,
            "attribute_line_ids": [Command.create({
                "attribute_id": cls.attribute.id,
                "value_ids": [Command.set(cls.attribute.value_ids.ids)],
            })],
        })
        cls.variant = cls.product.product_variant_id
        cls.optional_value = cls.product.attribute_line_ids.product_template_value_ids[:1]

    # ------------------------------------------------------------------
    # Talking to the routes
    # ------------------------------------------------------------------
    def _json(self, url, values):
        """Post a JSON-RPC envelope, the way the shop's own JavaScript does."""
        body = {"jsonrpc": "2.0", "method": "call", "params": values}
        response = self.url_open(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text[:400])
        payload = response.json()
        self.assertNotIn("error", payload, payload.get("error"))
        return payload.get("result") or {}

    def _csrf_token(self):
        page = self.url_open(self.product.website_url)
        return lxml_html.fromstring(page.text).xpath(
            "//input[@name='csrf_token']")[0].get("value")

    # ------------------------------------------------------------------
    # Reading the cart back
    # ------------------------------------------------------------------
    def _line(self, product):
        self.env.invalidate_all()
        order = self.env["sale.order"].search(
            [("website_id", "=", self.website.id), ("state", "=", "draft")],
            order="id desc", limit=1)
        return order.order_line.filtered(lambda line: line.product_id == product)

    def _stored_quantity(self, line):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT product_uom_qty FROM sale_order_line WHERE id = %s", [line.id])
        return self.env.cr.fetchone()[0]

    # ------------------------------------------------------------------
    # /shop/cart/update_json -- adding, and editing on the cart page
    # ------------------------------------------------------------------
    def test_the_ajax_route_keeps_the_step_on_an_optional_attribute(self):
        self._json("/shop/cart/update_json", {
            "product_id": self.variant.id,
            "add_qty": 2.25,
            "no_variant_attribute_value_ids": self.optional_value.ids,
        })
        line = self._line(self.variant)
        self.assertEqual(len(line), 1, "the product must be added exactly once")
        self.assertEqual(self._stored_quantity(line), 2.25)

    def test_setting_the_quantity_on_the_cart_page_keeps_the_step(self):
        self._json("/shop/cart/update_json", {
            "product_id": self.variant.id, "add_qty": 2,
            "no_variant_attribute_value_ids": self.optional_value.ids,
        })
        line = self._line(self.variant)
        self.assertEqual(self._stored_quantity(line), 2.0)
        self._json("/shop/cart/update_json", {
            "product_id": self.variant.id, "line_id": line.id, "set_qty": 2.25,
            "no_variant_attribute_value_ids": self.optional_value.ids,
        })
        self.assertEqual(self._stored_quantity(line), 2.25)

    # ------------------------------------------------------------------
    # /shop/cart/update -- the plain form, with the token the page carries
    # ------------------------------------------------------------------
    def test_the_form_route_keeps_the_step_on_an_optional_attribute(self):
        response = self.url_open("/shop/cart/update", data={
            "csrf_token": self._csrf_token(),
            "product_id": self.variant.id,
            "add_qty": 2.25,
            "no_variant_attribute_values": json.dumps(
                [{"value": self.optional_value.id}]),
        })
        self.assertEqual(response.status_code, 200)
        line = self._line(self.variant)
        self.assertEqual(len(line), 1, "the product must be added exactly once")
        self.assertEqual(self._stored_quantity(line), 2.25)
