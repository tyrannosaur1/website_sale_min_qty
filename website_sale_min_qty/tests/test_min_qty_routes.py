# -*- coding: utf-8 -*-
"""The routes, not just the model.

The model tests prove the arithmetic; they say nothing about whether a route
reaches it. Each entry point that can put a quantity in the cart is exercised
here against a product that carries an optional (``no_variant``) attribute --
the case the core's "no floats in ecommerce" cast used to swallow -- and the
quantity read back is the one PostgreSQL stores.

2.25 is deliberate: it is on a 0.25 grid but truncates to 2, which is also on
the grid, so only a comparison with the typed value can tell the two apart.
"""
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

    def _add(self, product, quantity, variant=None, **values):
        return self.make_jsonrpc_request("/shop/cart/add", dict(
            values,
            product_template_id=product.id,
            product_id=(variant or product.product_variant_id).id,
            quantity=quantity,
        ))

    # ------------------------------------------------------------------
    # /shop/cart/add
    # ------------------------------------------------------------------
    def test_the_add_route_keeps_the_step_on_an_optional_attribute(self):
        self._add(self.product, 2.25,
                  no_variant_attribute_value_ids=self.optional_value.ids)
        line = self._line(self.variant)
        self.assertEqual(len(line), 1, "the product must be added exactly once")
        self.assertEqual(self._stored_quantity(line), 2.25)

    def test_the_add_route_keeps_the_step_on_a_custom_attribute(self):
        attribute = self.env["product.attribute"].create({
            "name": "Engraving",
            "create_variant": "dynamic",
            "value_ids": [Command.create({"name": "Text", "is_custom": True})],
        })
        product = self.env["product.template"].create({
            "name": "Engraved Nuts",
            "type": "consu",
            "sale_ok": True,
            "list_price": 10.0,
            "qty_step": 0.25,
            "website_published": True,
            "attribute_line_ids": [Command.create({
                "attribute_id": attribute.id,
                "value_ids": [Command.set(attribute.value_ids.ids)],
            })],
        })
        value = product.attribute_line_ids.product_template_value_ids[:1]
        # A dynamic attribute only gets a variant when one is asked for.
        variant = (product.product_variant_ids[:1]
                   or product._create_product_variant(
                       product.attribute_line_ids.product_template_value_ids))
        self._add(product, 2.25, variant=variant, product_custom_attribute_values=[{
            "custom_product_template_attribute_value_id": value.id,
            "custom_value": "Anna",
        }])
        line = self._line(variant)
        self.assertEqual(len(line), 1, "the customised product must be added once")
        self.assertEqual(self._stored_quantity(line), 2.25)

    def test_the_add_route_keeps_the_step_on_a_combo(self):
        item_product = self.env["product.template"].create({
            "name": "Combo Item", "type": "consu", "sale_ok": True,
            "list_price": 4.0, "website_published": True,
        })
        combo = self.env["product.combo"].create({
            "name": "One choice",
            "combo_item_ids": [Command.create(
                {"product_id": item_product.product_variant_id.id})],
        })
        parent = self.env["product.template"].create({
            "name": "Combo Box", "type": "combo", "sale_ok": True,
            "list_price": 25.0, "qty_step": 0.25, "website_published": True,
            "combo_ids": [Command.link(combo.id)],
        })
        item = combo.combo_item_ids[:1]
        self._add(parent, 2.25, linked_products=[{
            "product_template_id": item_product.id,
            "parent_product_template_id": parent.id,
            "quantity": 2.25,
            "product_id": item_product.product_variant_id.id,
            "combo_item_id": item.id,
            "no_variant_attribute_value_ids": [],
            "product_custom_attribute_values": [],
        }])
        line = self._line(parent.product_variant_id)
        self.assertEqual(len(line), 1, "the combo must be added exactly once")
        self.assertEqual(self._stored_quantity(line), 2.25)

    # ------------------------------------------------------------------
    # /shop/cart/update
    # ------------------------------------------------------------------
    def test_the_update_route_keeps_the_step(self):
        self._add(self.product, 2, no_variant_attribute_value_ids=self.optional_value.ids)
        line = self._line(self.variant)
        self.assertEqual(self._stored_quantity(line), 2.0)
        self.make_jsonrpc_request("/shop/cart/update", {
            "line_id": line.id,
            "quantity": 2.25,
        })
        self.assertEqual(self._stored_quantity(line), 2.25)
