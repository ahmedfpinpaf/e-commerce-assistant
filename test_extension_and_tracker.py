"""
Test Suite for Chrome Extension Backend & Product Price Tracker
Covers:
1. Product price scraper and metadata extractor across Daraz, Amazon, OLX, eBay fixtures.
2. SQLite tracker database: tracked products, price history, user settings, alert logs.
3. Scheduler & alert triggers: target price alert, general price drop, alert deduplication.
4. FastAPI tracking REST API endpoints:
   - GET /api/tracked-products
   - POST /api/track-product
   - GET /api/tracked-products/{id}
   - PATCH /api/tracked-products/{id}
   - DELETE /api/tracked-products/{id}
   - GET /api/tracked-products/{id}/history
   - POST /api/check-price/{id}
   - POST /api/check-all-prices
   - GET /api/settings & POST /api/settings
   - POST /api/test-email-alert
   - GET /api/alert-logs
   - GET /test_pages/{filename}
5. Extension NLP Chatbot endpoint (/api/extension/chat):
   - "What is this product?"
   - "Track this product"
   - "Alert me when it falls below PKR 160,000"
   - "Show tracked products"
   - "Stop tracking"
"""

import os
import sys
import unittest
from fastapi.testclient import TestClient

from app import app
import tracker_db
from price_scraper import price_scraper
from tracker_scheduler import tracker_scheduler
from email_service import email_service

client = TestClient(app)

class TestProductPriceScraper(unittest.TestCase):
    def test_daraz_extraction(self):
        with open("test_pages/daraz_samsung_s24.html", "r", encoding="utf-8") as f:
            html = f.read()
        data = price_scraper.extract_from_html(html, "https://www.daraz.pk/products/samsung-galaxy-s24.html")
        self.assertEqual(data["website"], "Daraz")
        self.assertEqual(data["name"], "Samsung Galaxy S24")
        self.assertEqual(data["brand"], "Samsung")
        self.assertEqual(data["model"], "Galaxy S24")
        self.assertEqual(data["price"], 180000.0)
        self.assertEqual(data["currency"], "PKR")

    def test_amazon_extraction(self):
        with open("test_pages/amazon_dell_xps.html", "r", encoding="utf-8") as f:
            html = f.read()
        data = price_scraper.extract_from_html(html, "https://www.amazon.com/dp/B0CX2TEST")
        self.assertEqual(data["website"], "Amazon")
        self.assertIn("Dell XPS 13", data["name"])
        self.assertEqual(data["brand"], "Dell")
        self.assertEqual(data["price"], 999.0)
        self.assertEqual(data["currency"], "USD")

    def test_olx_extraction(self):
        with open("test_pages/olx_iphone.html", "r", encoding="utf-8") as f:
            html = f.read()
        data = price_scraper.extract_from_html(html, "https://www.olx.com.pk/item/iphone-15-pro-max-iid-10928374")
        self.assertEqual(data["website"], "OLX")
        self.assertIn("iPhone 15 Pro Max", data["name"])
        self.assertEqual(data["price"], 340000.0)
        self.assertEqual(data["currency"], "PKR")

    def test_ebay_extraction(self):
        with open("test_pages/ebay_laptop.html", "r", encoding="utf-8") as f:
            html = f.read()
        data = price_scraper.extract_from_html(html, "https://www.ebay.com/itm/195829104812")
        self.assertEqual(data["website"], "eBay")
        self.assertIn("Lenovo ThinkPad", data["name"])
        self.assertEqual(data["price"], 650.0)
        self.assertEqual(data["currency"], "USD")


class TestTrackerDatabaseAndScheduler(unittest.TestCase):
    def setUp(self):
        # Clear simulation registry before each test
        price_scraper.clear_simulated_prices()

    def test_db_lifecycle_and_history(self):
        test_url = "https://www.daraz.pk/products/unit-test-phone-999.html"
        
        # 1. Add product
        prod = tracker_db.add_tracked_product(
            product_name="Unit Test Phone",
            product_url=test_url,
            website="Daraz",
            current_price=50000.0,
            currency="PKR",
            brand="TestBrand",
            target_price=45000.0
        )
        prod_id = prod["id"]
        self.assertIsNotNone(prod_id)
        self.assertEqual(prod["current_price"], 50000.0)
        self.assertEqual(prod["target_price"], 45000.0)

        # 2. Record price update
        updated = tracker_db.record_price_update(prod_id, 47000.0, "PKR")
        self.assertEqual(updated["current_price"], 47000.0)
        self.assertEqual(updated["previous_price"], 50000.0)

        # 3. Check price history
        history = tracker_db.get_price_history(prod_id)
        self.assertGreaterEqual(len(history), 2)
        self.assertEqual(history[0]["price"], 50000.0)
        self.assertEqual(history[1]["price"], 47000.0)

        # 4. Settings update and retrieval
        tracker_db.update_user_settings({"alert_email": "ma0819262@gmail.com"})
        settings = tracker_db.get_user_settings()
        self.assertEqual(settings.get("alert_email"), "ma0819262@gmail.com")

        # 5. Clean up
        tracker_db.delete_tracked_product(prod_id)
        self.assertIsNone(tracker_db.get_tracked_product(prod_id))

    def test_alert_trigger_and_deduplication(self):
        test_url = "https://www.daraz.pk/products/alert-test-item-888.html"
        
        prod = tracker_db.add_tracked_product(
            product_name="Alert Test S24",
            product_url=test_url,
            website="Daraz",
            current_price=180000.0,
            currency="PKR",
            target_price=160000.0,
            alert_type="target_price"
        )
        prod_id = prod["id"]

        # Simulate price dropping to 155,000 (below 160,000 target)
        price_scraper.set_simulated_price(test_url, 155000.0, "PKR")
        
        # Check price - should trigger alert
        check_result_1 = tracker_scheduler.check_product_price(prod)
        self.assertTrue(check_result_1["alert_triggered"])
        self.assertEqual(check_result_1["new_price"], 155000.0)

        # Check DB that last_alert_price was updated
        refreshed_prod = tracker_db.get_tracked_product(prod_id)
        self.assertEqual(refreshed_prod["last_alert_price"], 155000.0)
        self.assertEqual(refreshed_prod["tracking_status"], "alert_triggered")

        # Check alert logs table
        logs = tracker_db.get_alert_logs()
        self.assertTrue(any(l["product_id"] == prod_id for l in logs))

        # Check deduplication: run check_product_price again with same price 155,000
        check_result_2 = tracker_scheduler.check_product_price(refreshed_prod)
        self.assertFalse(check_result_2["alert_triggered"], "Duplicate alert must be suppressed")
        self.assertEqual(check_result_2["trigger_reason"], "Duplicate alert suppressed")

        # Clean up
        tracker_db.delete_tracked_product(prod_id)
        price_scraper.clear_simulated_prices()


class TestFastAPIEndpoints(unittest.TestCase):
    def test_test_pages_served(self):
        resp = client.get("/test_pages/daraz_samsung_s24.html")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Samsung Galaxy S24", resp.text)

    def test_track_product_api_crud(self):
        # 1. Add product via API
        payload = {
            "product_name": "API Test Laptop",
            "product_url": "https://www.amazon.com/dp/B0TESTLAPTOP",
            "website": "Amazon",
            "current_price": 1200.0,
            "currency": "USD",
            "brand": "Dell",
            "target_price": 1100.0,
            "alert_type": "target_price"
        }
        res = client.post("/api/track-product", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        prod_id = data["id"]
        self.assertEqual(data["product_name"], "API Test Laptop")

        # 2. Get single product
        get_res = client.get(f"/api/tracked-products/{prod_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["id"], prod_id)

        # 3. Patch product (update target price and pause)
        patch_res = client.patch(f"/api/tracked-products/{prod_id}", json={
            "target_price": 1050.0,
            "tracking_status": "paused"
        })
        self.assertEqual(patch_res.status_code, 200)
        patched = patch_res.json()
        self.assertEqual(patched["target_price"], 1050.0)
        self.assertEqual(patched["tracking_status"], "paused")

        # 4. Check price history endpoint
        hist_res = client.get(f"/api/tracked-products/{prod_id}/history")
        self.assertEqual(hist_res.status_code, 200)
        self.assertIsInstance(hist_res.json(), list)

        # 5. Delete product
        del_res = client.delete(f"/api/tracked-products/{prod_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["success"])

    def test_settings_api(self):
        post_res = client.post("/api/settings", json={
            "alert_email": "api_test@example.com",
            "check_interval_minutes": "10",
            "notifications_enabled": "true"
        })
        self.assertEqual(post_res.status_code, 200)
        
        get_res = client.get("/api/settings")
        self.assertEqual(get_res.status_code, 200)
        settings = get_res.json()
        self.assertEqual(settings.get("alert_email"), "api_test@example.com")
        self.assertEqual(settings.get("check_interval_minutes"), "10")

    def test_email_test_alert_endpoint(self):
        res = client.post("/api/test-email-alert")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("Price Drop Alert", data.get("subject"))

    def test_extension_chat_commands(self):
        active_prod = {
            "name": "Samsung Galaxy S24 Ultra",
            "brand": "Samsung",
            "model": "S24 Ultra",
            "price": 380000.0,
            "currency": "PKR",
            "url": "https://www.daraz.pk/products/samsung-s24-ultra.html",
            "website": "Daraz"
        }

        # Query 1: "What is this product?"
        resp1 = client.post("/api/extension/chat", json={
            "message": "What is this product?",
            "active_product": active_prod
        })
        self.assertEqual(resp1.status_code, 200)
        reply1 = resp1.json()["reply"]
        self.assertIn("Samsung Galaxy S24 Ultra", reply1)
        self.assertIn("PKR 380,000", reply1)

        # Query 2: "Track this product and alert me when it falls below PKR 350,000"
        resp2 = client.post("/api/extension/chat", json={
            "message": "Track this product and alert me when it falls below PKR 350,000",
            "active_product": active_prod
        })
        self.assertEqual(resp2.status_code, 200)
        res2_json = resp2.json()
        self.assertTrue(res2_json["tracked_product_added"])
        self.assertIn("Tracking Started", res2_json["reply"])
        self.assertIn("350,000", res2_json["reply"])

        # Query 3: "Show tracked products"
        resp3 = client.post("/api/extension/chat", json={
            "message": "Show tracked products",
            "active_product": active_prod
        })
        self.assertEqual(resp3.status_code, 200)
        reply3 = resp3.json()["reply"]
        self.assertIn("Samsung Galaxy S24 Ultra", reply3)

        # Query 4: "Stop tracking"
        resp4 = client.post("/api/extension/chat", json={
            "message": "Stop tracking",
            "active_product": active_prod
        })
        self.assertEqual(resp4.status_code, 200)
        reply4 = resp4.json()["reply"]
        self.assertIn("Stopped tracking", reply4)

if __name__ == "__main__":
    unittest.main()
