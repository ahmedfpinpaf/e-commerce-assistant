import time
import threading
import logging
from typing import Dict, Any, List

import tracker_db
from price_scraper import price_scraper
from email_service import email_service

logger = logging.getLogger("tracker_scheduler")

class PriceTrackingScheduler:
    def __init__(self):
        self._running = False
        self._thread = None
        self._interval_seconds = 300  # Default 5 minutes

    def start(self, interval_seconds: int = 300):
        if self._running:
            return
        self._interval_seconds = interval_seconds
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="PriceTrackerWorker")
        self._thread.start()
        logger.info(f"Price tracker background scheduler started (interval: {interval_seconds}s)")

    def stop(self):
        self._running = False

    def _run_loop(self):
        while self._running:
            try:
                self.check_all_active_products()
            except Exception as e:
                logger.error(f"Error in tracking scheduler loop: {e}")
            
            # Sleep in small increments for responsive shutdown
            for _ in range(self._interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

    def check_product_price(self, prod: Dict[str, Any]) -> Dict[str, Any]:
        """
        Checks a single product's URL, updates price history,
        and triggers email alert if conditions are met.
        """
        prod_id = prod["id"]
        url = prod["product_url"]
        name = prod["product_name"]
        curr_price = float(prod.get("current_price") or 0.0)
        target_price = float(prod["target_price"]) if prod.get("target_price") is not None else None
        last_alert_price = float(prod["last_alert_price"]) if prod.get("last_alert_price") is not None else None
        currency = prod.get("currency") or "PKR"
        alert_type = prod.get("alert_type") or "target_price"

        # 1. Scrape latest price from URL
        scraped = price_scraper.scrape_product_info(url)
        new_price = scraped.get("price")
        
        if new_price is None or new_price <= 0:
            logger.warning(f"Could not retrieve price for '{name}' at {url}")
            return {
                "product_id": prod_id,
                "status": "failed_fetch",
                "error": scraped.get("error", "No price found")
            }

        new_currency = scraped.get("currency") or currency

        # 2. Record updated price in DB
        updated_prod = tracker_db.record_price_update(prod_id, new_price, new_currency)

        # 3. Check trigger conditions
        alert_triggered = False
        trigger_reason = None

        # Condition A: Target price alert
        if target_price is not None and new_price <= target_price:
            alert_triggered = True
            trigger_reason = f"Price reached target (Current: {new_price} <= Target: {target_price})"

        # Condition B: General price-drop tracking (or if alert_type == 'any_drop')
        elif (alert_type == "any_drop" or target_price is None) and new_price < curr_price:
            alert_triggered = True
            trigger_reason = f"Price dropped from {curr_price} to {new_price}"

        # Deduplication check: Do NOT repeatedly send the same alert for the same unchanged price
        if alert_triggered and last_alert_price is not None and abs(last_alert_price - new_price) < 0.01:
            logger.info(f"Skipping duplicate alert for '{name}': already alerted at price {new_price}")
            alert_triggered = False
            trigger_reason = "Duplicate alert suppressed"

        email_result = None
        if alert_triggered:
            logger.info(f"ALERT TRIGGERED for '{name}': {trigger_reason}")
            email_result = email_service.send_price_drop_alert(
                product_id=prod_id,
                product_name=name,
                product_url=url,
                current_price=new_price,
                previous_price=curr_price,
                currency=new_currency,
                target_price=target_price
            )

        return {
            "product_id": prod_id,
            "product_name": name,
            "previous_price": curr_price,
            "new_price": new_price,
            "currency": new_currency,
            "target_price": target_price,
            "alert_triggered": alert_triggered,
            "trigger_reason": trigger_reason,
            "email_result": email_result
        }

    def check_all_active_products(self) -> List[Dict[str, Any]]:
        products = tracker_db.get_all_tracked_products()
        results = []
        for prod in products:
            if prod.get("tracking_status") != "paused":
                res = self.check_product_price(prod)
                results.append(res)
        return results

tracker_scheduler = PriceTrackingScheduler()
