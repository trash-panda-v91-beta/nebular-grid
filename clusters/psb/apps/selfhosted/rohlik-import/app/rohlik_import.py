#!/usr/bin/env python3
"""Import the Rohlik basket into Sparky foods.

Reads the current cart plus the last few delivered orders, pulls per-100 g
nutrition off each product, and writes the ones Sparky does not have yet.

Exit codes, because the difference matters for alerting:
  0  ok, nothing new, or skipped (Sparky not ready)
  1  failed (Rohlik auth, unexpected API shape, Sparky write refused)
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time

import httpx

SPARKY = os.environ.get("SPARKY_URL", "http://sparkyfitness.selfhosted.svc.cluster.local:3010")
SPARKY_KEY = os.environ.get("SPARKY_API_KEY", "")
ROHLIK_USER = os.environ.get("ROHLIK_USER", "")
ROHLIK_PASSWORD = os.environ.get("ROHLIK_PASSWORD", "")
ORDER_PAGES = int(os.environ.get("ROHLIK_ORDER_PAGES", "1"))
ORDERS_PER_PAGE = int(os.environ.get("ROHLIK_ORDERS_PER_PAGE", "10"))
HEALTH_WAIT = int(os.environ.get("SPARKY_HEALTH_WAIT", "600"))

SPARKY_HEADERS = {"Authorization": f"Bearer {SPARKY_KEY}", "Content-Type": "application/json"}

# Czech and English label fragments per nutrient, matched case-insensitively.
TOKENS = {
    "calories": ("energie", "energy", "kcal"),
    "protein": ("bílkovin", "bilkovin", "protein"),
    "carbs": ("sacharid", "carbohydrate", "carbs"),
    "sugars": ("cukr", "sugar"),
    "fat": ("tuk", "fat"),
    "saturated_fat": ("nasycen", "saturat"),
    "dietary_fiber": ("vláknin", "vlaknin", "fibre", "fiber"),
    "salt": ("sůl", "sul", "salt"),
}


def log(msg: str) -> None:
    print(msg, flush=True)


def die(msg: str) -> None:
    print(f"failed: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


async def wait_for_sparky() -> bool:
    """Bounded wait so a restart elsewhere does not become a page."""
    deadline = time.monotonic() + HEALTH_WAIT
    while True:
        try:
            r = httpx.get(f"{SPARKY}/api/health", timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(15)


def flatten(node, path=""):
    """Yield (path, key, value) for every scalar in a nested structure."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from flatten(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from flatten(v, f"{path}[{i}]")
    else:
        yield path, path.split(".")[-1].split("[")[0], node


def numbers(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", text)]


def extract_nutrients(composition) -> dict:
    """Map whatever shape Rohlik returns onto our nutrient names.

    Accepts strings like '1234 kJ / 295 kcal', '1.2 g' and bare numbers.
    Returns only what it actually found.
    """
    found: dict[str, float] = {}
    scalar = list(flatten(composition))

    for ours, tokens in TOKENS.items():
        for path, key, value in scalar:
            hay = f"{path} {key}".lower()
            if not any(t in hay for t in tokens):
                continue
            if isinstance(value, (int, float)):
                found[ours] = float(value)
                break
            if not isinstance(value, str):
                continue
            low = value.lower()
            # energy is often 'X kJ / Y kcal' - take the kcal half
            if "kcal" in low:
                m = re.search(r"([\d.,]+)\s*kcal", low)
                if m:
                    found[ours] = float(m.group(1).replace(",", "."))
                    break
            elif ours == "calories" and "kj" in low:
                continue
            nums = numbers(low)
            if nums:
                found[ours] = nums[0]
                break
    return found


def sparky_has_barcode(ean: str) -> bool:
    try:
        r = httpx.get(f"{SPARKY}/api/v2/foods/barcode/{ean}", headers=SPARKY_HEADERS, timeout=15)
    except Exception:
        return False
    if r.status_code != 200:
        return False
    try:
        body = r.json()
    except Exception:
        return False
    return bool(body) and body.get("error") is None


def sparky_search(name: str) -> bool:
    try:
        r = httpx.get(f"{SPARKY}/api/foods", headers=SPARKY_HEADERS,
                      params={"search": name, "limit": 5}, timeout=15)
        body = r.json()
    except Exception:
        return False
    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return False
    low = name.lower()
    return any(low == str(row.get("name", "")).lower() for row in rows if isinstance(row, dict))


def sparky_import(foods: list[dict]) -> None:
    r = httpx.post(f"{SPARKY}/api/foods/import-from-csv", headers=SPARKY_HEADERS,
                   json={"foods": foods, "overwrite": False}, timeout=120)
    if r.status_code != 200:
        die(f"sparky import returned {r.status_code}: {r.text[:300]}")


async def collect_products(client) -> dict[int, str]:
    """product_id -> a name to report with, from the cart and recent orders."""
    products: dict[int, str] = {}

    def add(item):
        for key in ("productId", "product_id", "id"):
            if isinstance(item, dict) and item.get(key):
                products[int(item[key])] = str(item.get("name") or item.get("productName") or "")
                return

    try:
        cart = await client.cart.get_content()
        for item in (cart or {}).get("items", []) if isinstance(cart, dict) else []:
            add(item)
    except Exception as exc:
        log(f"cart read failed, continuing with orders: {exc}")

    try:
        for page in range(ORDER_PAGES):
            orders = await client.orders.get_delivered(limit=ORDERS_PER_PAGE, offset=page * ORDERS_PER_PAGE)
            if not orders:
                break
            for order in orders:
                order_id = order.get("orderId") or order.get("id")
                if not order_id:
                    continue
                detail = await client.orders.get_detail(order_id=order_id)
                for item in (detail or {}).get("items", []) if isinstance(detail, dict) else []:
                    add(item)
    except Exception as exc:
        log(f"order read failed: {exc}")

    return products


async def main() -> int:
    for name, value in (("SPARKY_API_KEY", SPARKY_KEY), ("ROHLIK_USER", ROHLIK_USER),
                        ("ROHLIK_PASSWORD", ROHLIK_PASSWORD)):
        if not value:
            die(f"{name} is not set")

    if not await wait_for_sparky():
        log(f"skipped: Sparky not ready after {HEALTH_WAIT}s")
        return 0

    from rohlik_api import RohlikAPI

    async with RohlikAPI(username=ROHLIK_USER, password=ROHLIK_PASSWORD) as client:
        products = await collect_products(client)
        log(f"basket: {len(products)} products")

        rows, missing, already = [], [], 0
        for product_id, label in sorted(products.items()):
            try:
                detail = await client.products.get_detail(product_id=product_id) or {}
                composition = await client.products.get_composition(product_id=product_id)
            except Exception as exc:
                missing.append(f"{label or product_id} (lookup failed: {exc})")
                continue

            nutrients = extract_nutrients(composition) if composition else {}
            if not nutrients.get("calories"):
                missing.append(label or str(product_id))
                continue

            ean = str(detail.get("ean") or detail.get("barcode") or "").strip() or None
            name = str(detail.get("name") or label or f"Rohlik {product_id}")
            brand = str(detail.get("brand") or "").strip() or None

            if ean and sparky_has_barcode(ean):
                already += 1
                continue
            if not ean and sparky_search(name):
                already += 1
                continue

            row = {
                "name": name,
                "brand": brand,
                "barcode": ean,
                "serving_size": 100,
                "serving_unit": "g",
                "calories": nutrients["calories"],
                "protein": nutrients.get("protein"),
                "carbs": nutrients.get("carbs"),
                "fat": nutrients.get("fat"),
                "saturated_fat": nutrients.get("saturated_fat"),
                "dietary_fiber": nutrients.get("dietary_fiber"),
                "sugars": nutrients.get("sugars"),
                "source": "rohlik",
                "provider_external_id": str(product_id),
                "provider_verified": False,
                "is_custom": True,
            }
            if nutrients.get("salt") is not None:
                row["sodium"] = round(nutrients["salt"] * 400)
            rows.append(row)

        if rows:
            sparky_import(rows)

    log(f"added {len(rows)}, already there {already}, no nutrition {len(missing)}")
    if missing:
        log("no nutrition data (check these by hand):")
        for name in missing:
            log(f"  - {name}")

    # Nothing mapped at all on a non-empty basket is a shape change, not an empty shop.
    if products and not rows and not already and missing:
        die("every product failed to map, the Rohlik response shape probably changed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
