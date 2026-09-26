"""Independent business-oracle tests, derived from CONTRACT.md only."""

from collections import Counter
from copy import deepcopy
import random
import unittest

try:
    from experiments.online_cutover.model import Model
except ModuleNotFoundError as error:
    if error.name != "experiments.online_cutover.model":
        raise
    Model = None


def line(sku="A", quantity=1, price=10):
    return {"sku": sku, "quantity": quantity, "unit_price_cents": price}


def create(request="r1", order="o1", customer="Ada", lines=None):
    return {"op": "create", "request_id": request, "order_id": order,
            "customer": customer, "lines": [line()] if lines is None else lines}


def replace(request="r2", order="o1", revision=1, customer="Bea", lines=None):
    return {"op": "replace", "request_id": request, "order_id": order,
            "expected_revision": revision, "customer": customer,
            "lines": [line()] if lines is None else lines}


def delete(request="r3", order="o1", revision=1):
    return {"op": "delete", "request_id": request, "order_id": order,
            "expected_revision": revision}


def rejection(code):
    return {"ok": False, "error": code}


class GoldenBusinessTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Model, "independent business model is not implemented")
        self.model = Model({"B": 2, "A": 5, "Z": 0})

    def state(self):
        return (self.model.orders, self.model.receipts,
                self.model.apply({"op": "inventory"}))

    def test_empty_reads_have_exact_schema_and_sorted_inventory(self):
        self.assertEqual(self.model.apply({"op": "get", "order_id": "absent"}),
                         {"ok": True, "order": None})
        self.assertEqual(self.model.apply({"op": "inventory"}), {
            "ok": True, "stock": [
                {"sku": "A", "capacity": 5, "available": 5},
                {"sku": "B", "capacity": 2, "available": 2},
                {"sku": "Z", "capacity": 0, "available": 0}]})
        self.assertEqual(self.model.apply({"op": "health"}),
                         {"ok": True, "backend": "source"})
        self.model.backend = "target"
        self.assertEqual(self.model.apply({"op": "health"}),
                         {"ok": True, "backend": "target"})
        self.assertEqual(self.model.receipts, {})

    def test_create_keeps_line_order_and_exact_total(self):
        body = create(lines=[line("B", 2, 125), line("A", 3, 7)])
        order = {"order_id": "o1", "customer": "Ada", "revision": 1,
                 "lines": [line("B", 2, 125), line("A", 3, 7)], "total_cents": 271}
        response = {"ok": True, "order": order}
        self.assertEqual(self.model.apply(body), response)
        self.assertEqual(self.model.apply({"op": "get", "order_id": "o1"}), response)
        self.assertEqual(self.model.orders, {"o1": order})
        self.assertEqual(self.model.receipts, {"r1": {"body": body, "response": response}})
        self.assertEqual([s["available"] for s in self.model.apply({"op": "inventory"})["stock"]], [2, 0, 0])

    def test_replace_releases_old_stock_atomically_and_changes_line_order(self):
        self.model.apply(create(lines=[line("A", 5, 2), line("B", 1, 9)]))
        body = replace(lines=[line("B", 2, 0), line("A", 4, 3)])
        expected = {"ok": True, "order": {"order_id": "o1", "customer": "Bea",
                    "revision": 2, "lines": [line("B", 2, 0), line("A", 4, 3)],
                    "total_cents": 12}}
        self.assertEqual(self.model.apply(body), expected)
        self.assertEqual([s["available"] for s in self.model.apply({"op": "inventory"})["stock"]], [1, 0, 0])

    def test_insufficient_replace_rolls_back_every_sku_and_preserves_receipt(self):
        self.model.apply(create(lines=[line("A", 5), line("B", 1)]))
        before_orders, _, before_inventory = self.state()
        body = replace(lines=[line("A", 1), line("B", 3)])
        self.assertEqual(self.model.apply(body), rejection("insufficient_stock"))
        self.assertEqual(self.model.orders, before_orders)
        self.assertEqual(self.model.apply({"op": "inventory"}), before_inventory)
        self.assertEqual(self.model.receipts["r2"], {"body": body, "response": rejection("insufficient_stock")})

    def test_delete_releases_and_recreate_restarts_revision(self):
        self.model.apply(create(lines=[line("A", 5)]))
        removed = delete()
        self.assertEqual(self.model.apply(removed), {"ok": True, "deleted": "o1", "revision": 2})
        self.assertEqual(self.model.orders, {})
        self.assertEqual(self.model.apply(create("new", lines=[line("B", 2)]))["order"]["revision"], 1)
        self.assertEqual(self.model.apply(removed), {"ok": True, "deleted": "o1", "revision": 2})
        self.assertEqual(self.model.orders["o1"]["lines"], [line("B", 2)])

    def test_success_receipts_replay_historical_responses_after_all_mutations(self):
        first = create(lines=[line("A", 2, 7)])
        second = replace(lines=[line("B", 1, 9)])
        third = delete(revision=2)
        expected = [
            {"ok": True, "order": {"order_id": "o1", "customer": "Ada", "revision": 1,
                                  "lines": [line("A", 2, 7)], "total_cents": 14}},
            {"ok": True, "order": {"order_id": "o1", "customer": "Bea", "revision": 2,
                                  "lines": [line("B", 1, 9)], "total_cents": 9}},
            {"ok": True, "deleted": "o1", "revision": 3}]
        for body, answer in zip([first, second, third], expected):
            self.assertEqual(self.model.apply(body), answer)
        self.model.apply(create("new", lines=[line("Z")]))  # Durable rejection.
        self.model.apply(create("recreated", lines=[line("A", 5, 3)]))
        before = self.state()
        for body, answer in zip([first, second, third], expected):
            self.assertEqual(self.model.apply(dict(reversed(list(body.items())))), answer)
        self.assertEqual(self.state(), before)

    def test_business_error_precedence_and_all_rejected_receipts(self):
        self.model.apply(create())
        cases = [
            (create("exists", lines=[line("Z")]), "exists"),
            (replace("missing", "absent", 999, lines=[line("Z")]), "missing"),
            (replace("stale", revision=999, lines=[line("Z")]), "stale_revision"),
            (replace("stock", lines=[line("Z")]), "insufficient_stock"),
            (delete("dm", "absent", 999), "missing"),
            (delete("ds", revision=999), "stale_revision")]
        original_orders = self.model.orders
        for body, error in cases:
            self.assertEqual(self.model.apply(body), rejection(error))
            self.assertEqual(self.model.receipts[body["request_id"]], {"body": body, "response": rejection(error)})
            self.assertEqual(self.model.orders, original_orders)
        self.model.apply(delete("remove"))
        before = self.state()
        for body, error in cases:
            self.assertEqual(self.model.apply(body), rejection(error))
        self.assertEqual(self.state(), before)

    def test_rejected_missing_and_stock_requests_do_not_succeed_on_retry(self):
        missing = delete("missing", "later")
        stock = create("stock", "later", lines=[line("A", 6)])
        self.assertEqual(self.model.apply(missing), rejection("missing"))
        self.assertEqual(self.model.apply(stock), rejection("insufficient_stock"))
        self.model.apply(create("new", "later"))
        self.assertEqual(self.model.apply(missing), rejection("missing"))
        self.assertEqual(self.model.apply(stock), rejection("insufficient_stock"))
        self.assertIn("later", self.model.orders)

    def test_request_conflict_precedes_current_business_state(self):
        original = create()
        self.model.apply(original)
        before = self.state()
        changed = create(customer="Changed", lines=[line("Z")])
        self.assertEqual(self.model.apply(changed), rejection("request_conflict"))
        self.assertEqual(self.model.apply(delete("r1", "missing", 9)), rejection("request_conflict"))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.model.apply(original), before[1]["r1"]["response"])

    def test_validation_precedes_existing_receipt_and_creates_none(self):
        self.model.apply(create())
        before = self.state()
        for body in [create(lines=[line("UNKNOWN")]), create(lines=[line(quantity=True)]),
                     dict(create(), unexpected=3), dict(delete(), expected_revision=1.0)]:
            with self.subTest(body=body):
                self.assertEqual(self.model.apply(body), rejection("invalid_request"))
                self.assertEqual(self.state(), before)

    def test_array_order_changes_request_identity(self):
        first = create(lines=[line("B"), line("A")])
        answer = self.model.apply(first)
        reordered = deepcopy(first)
        reordered["lines"] = list(reversed(reordered["lines"]))
        self.assertEqual(self.model.apply(reordered), rejection("request_conflict"))
        self.assertEqual(self.model.apply(first), answer)

    def test_inputs_outputs_and_exported_state_never_alias_internal_state(self):
        body = create(lines=[line("B"), line("A", 2)])
        original = deepcopy(body)
        response = self.model.apply(body)
        expected = deepcopy(response)
        body["lines"][0]["quantity"] = 100
        response["order"]["lines"].clear()
        exported_orders = self.model.orders
        exported_receipts = self.model.receipts
        exported_orders["o1"]["customer"] = "Mutated"
        exported_receipts["r1"]["body"]["lines"].clear()
        exported_receipts["r1"]["response"]["order"].clear()
        self.assertEqual(self.model.apply(original), expected)
        got = self.model.apply({"op": "get", "order_id": "o1"})
        got["order"].clear()
        stock = self.model.apply({"op": "inventory"})
        stock["stock"][0]["available"] = -1
        self.assertEqual(self.model.apply({"op": "get", "order_id": "o1"}), expected)
        self.assertGreaterEqual(self.model.apply({"op": "inventory"})["stock"][0]["available"], 0)

    def test_seed_order_and_historical_receipt_are_owned_and_not_recomputed(self):
        prior = create()
        historical = {"ok": True, "order": {"order_id": "o1", "customer": "Ada",
            "revision": 1, "lines": [line()], "total_cents": 10}}
        current = {"order_id": "o1", "customer": "Later", "revision": 3,
                   "lines": [line("B", 2, 4)], "total_cents": 8}
        capacities = {"A": 5, "B": 2}
        orders = [current]
        receipts = {"r1": {"body": prior, "response": historical}}
        model = Model(capacities, orders, receipts, backend="target")
        expected = deepcopy(historical)
        capacities["A"] = 0
        current["lines"].clear()
        receipts["r1"]["response"].clear()
        self.assertEqual(model.apply(prior), expected)
        self.assertEqual(model.orders["o1"]["revision"], 3)
        self.assertEqual(model.apply({"op": "inventory"})["stock"], [
            {"sku": "A", "capacity": 5, "available": 5},
            {"sku": "B", "capacity": 2, "available": 0}])

    def test_large_money_and_revision_use_exact_integer_arithmetic(self):
        capacities = {f"S{n}": 1000000 for n in range(100)}
        model = Model(capacities)
        body = create(lines=[line(sku, 1000000, 1000000000) for sku in capacities])
        self.assertEqual(model.apply(body)["order"]["total_cents"], 100000000000000000)
        order = {"order_id": "o1", "customer": "Ada", "revision": 2**63 - 2,
                 "lines": [line()], "total_cents": 10}
        model = Model({"A": 1}, [order])
        answer = model.apply(replace(revision=2**63 - 2))
        self.assertEqual(answer["order"]["revision"], 2**63 - 1)
        self.assertEqual(model.apply(delete(revision=2**63 - 1)), rejection("invalid_request"))

    def test_validation_limits_types_exact_fields_and_unicode(self):
        invalid = [None, [], True, 1, "get", {}, {"op": []}, {"op": "unknown"},
            {"op": "inventory", "request_id": "r"}, {"op": "health", "extra": 1},
            {"op": "get"}, {"op": "get", "order_id": "has space"},
            create(request="x" * 65), create(order="é"), create(customer=""),
            create(customer="é" * 121), create(customer="NUL\x00name"),
            create(customer="\ud800"), create(customer="\udfff"),
            create(lines=[]), create(lines=[line()] * 2),
            create(lines=[line(quantity=0)]), create(lines=[line(quantity=1000001)]),
            create(lines=[line(quantity=1.0)]), create(lines=[line(quantity=True)]),
            create(lines=[line(price=-1)]), create(lines=[line(price=1000000001)]),
            create(lines=[line(price=False)]), create(lines=[line(price=0.0)]),
            create(lines=[dict(line(), extra=1)]), create(lines=[{"sku": "A"}]),
            create(lines="A"), create(lines=[None]), replace(revision=True),
            replace(revision=0), delete(revision=2**63 - 1)]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.model.apply(body), rejection("invalid_request"))
                self.assertEqual(self.model.orders, {})
                self.assertEqual(self.model.receipts, {})
        self.assertTrue(self.model.apply(create(customer="🧪" * 120))["ok"])
        self.assertTrue(Model({"A": 1}).apply(create(customer=" "))["ok"])

    def test_customer_is_not_normalized_or_trimmed(self):
        body = create(customer=" é ")
        answer = self.model.apply(body)
        self.assertEqual(answer["order"]["customer"], " é ")
        for customer in ["é", " e\u0301 "]:
            self.assertEqual(self.model.apply(create(customer=customer)), rejection("request_conflict"))


class RandomInvariantTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Model, "independent business model is not implemented")

    def test_random_mutations_preserve_stock_and_every_historical_receipt(self):
        for seed in range(12):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                capacities = {"A": 9, "B": 7, "C": 5}
                model = Model(capacities)
                history = {}
                for step in range(150):
                    order_id = f"o{rng.randrange(6)}"
                    op = rng.choice(["create", "replace", "delete"])
                    request_id = f"s{seed}_{step}"
                    skus = rng.sample(list(capacities), rng.randint(1, 3))
                    lines = [line(sku, rng.randint(1, 10), rng.randrange(200)) for sku in skus]
                    current = model.orders.get(order_id)
                    revision = current["revision"] if current and rng.random() < .75 else rng.randint(1, 6)
                    if op == "create":
                        body = create(request_id, order_id, f"customer{step}", lines)
                    elif op == "replace":
                        body = replace(request_id, order_id, revision, f"customer{step}", lines)
                    else:
                        body = delete(request_id, order_id, revision)
                    before_orders = model.orders
                    before_inventory = model.apply({"op": "inventory"})
                    answer = model.apply(body)
                    history[request_id] = {"body": deepcopy(body), "response": deepcopy(answer)}
                    self.assertEqual(model.receipts, history, (seed, step))
                    if not answer["ok"]:
                        self.assertEqual(model.orders, before_orders, (seed, step))
                        self.assertEqual(model.apply({"op": "inventory"}), before_inventory)
                    reserved = Counter()
                    for order in model.orders.values():
                        self.assertEqual(order["total_cents"], sum(x["quantity"] * x["unit_price_cents"] for x in order["lines"]))
                        for item in order["lines"]:
                            reserved[item["sku"]] += item["quantity"]
                    for stock in model.apply({"op": "inventory"})["stock"]:
                        self.assertEqual(stock["available"] + reserved[stock["sku"]], stock["capacity"])
                        self.assertGreaterEqual(stock["available"], 0)
                    if step % 11 == 0:
                        before = (model.orders, model.receipts, model.apply({"op": "inventory"}))
                        for receipt in history.values():
                            self.assertEqual(model.apply(receipt["body"]), receipt["response"])
                        self.assertEqual((model.orders, model.receipts, model.apply({"op": "inventory"})), before)
                    if step % 23 == 0:
                        model = Model(capacities, list(model.orders.values()), model.receipts)
                        self.assertEqual(model.receipts, history)


if __name__ == "__main__":
    unittest.main(verbosity=2)
