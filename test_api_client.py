from fastapi.testclient import TestClient
from app import app
import json

client = TestClient(app)

print("=== 1. Checking Exchange Rate Endpoint ===")
r_rate = client.get("/api/exchange-rate")
print("Status:", r_rate.status_code, "Payload:", r_rate.json())
assert r_rate.status_code == 200

print("\n=== 2. Checking Products Endpoint ===")
r_prod = client.get("/api/products")
print("Status:", r_prod.status_code, "Total products:", len(r_prod.json()))
assert r_prod.status_code == 200
assert len(r_prod.json()) == 214

print("\n=== 3. Conversational Test: Turn 1 (Item Request) ===")
# User says: "Mujhe Dell laptop chahiye"
r_turn1 = client.post("/api/chat", json={"message": "Mujhe Dell laptop chahiye"})
print("Turn 1 Status:", r_turn1.status_code)
d1 = r_turn1.json()
print("Turn 1 Bot Reply:\n", d1["reply"])
print("Turn 1 Products:", len(d1["products"]))
print("Turn 1 Stage:", d1["stage"])
print("Turn 1 State:", d1["state"])
assert d1["stage"] == "COLLECTING_SPECS"
assert len(d1["products"]) == 0
assert "processor" in d1["reply"].lower()

print("\n=== 4. Conversational Test: Turn 2 (Specs + Budget with Relaxation) ===")
# User says: "i7, 16GB RAM, 512GB SSD, budget 150000 PKR"
r_turn2 = client.post("/api/chat", json={
    "message": "i7, 16GB RAM, 512GB SSD, budget 150000 PKR",
    "state": d1["state"]
})
print("Turn 2 Status:", r_turn2.status_code)
d2 = r_turn2.json()
print("Turn 2 Bot Reply:\n", d2["reply"])
print("Turn 2 is_exact_match:", d2["is_exact_match"])
print("Turn 2 relaxed_spec:", d2["relaxed_spec"])
print("Turn 2 Products returned count:", len(d2["products"]))
for p in d2["products"]:
    print(f"  * {p['title']} | ${p['price']} USD (~Rs. {p['price_pkr']:,} PKR)")

assert d2["is_exact_match"] == False
assert d2["relaxed_spec"] == "budget"
assert len(d2["products"]) > 0

print("\n=== 5. Conversational Test: Turn 3 (Exact Match Mobile Query) ===")
r_turn3a = client.post("/api/chat", json={"message": "Mujhe mobile chahiye"})
d3a = r_turn3a.json()
print("Turn 3a ask specs:", d3a["reply"])

r_turn3b = client.post("/api/chat", json={
    "message": "Samsung, budget 150000 PKR",
    "state": d3a["state"]
})
d3b = r_turn3b.json()
print("Turn 3b reply:", d3b["reply"])
print("Turn 3b is_exact_match:", d3b["is_exact_match"])
print("Turn 3b Products returned count:", len(d3b["products"]))
for p in d3b["products"]:
    print(f"  * {p['title']} | ${p['price']} USD (~Rs. {p['price_pkr']:,} PKR)")

assert d3b["is_exact_match"] == True
assert len(d3b["products"]) >= 1

print("\n=== 6. Conversational Test: English Language Flow ===")
r_en1 = client.post("/api/chat", json={"message": "I want a laptop"})
d_en1 = r_en1.json()
print("English Turn 1 ask specs:\n", d_en1["reply"])
assert "processor" in d_en1["reply"].lower()

r_en2 = client.post("/api/chat", json={
    "message": "Dell, budget 150000 PKR",
    "state": d_en1["state"]
})
d_en2 = r_en2.json()
print("English Turn 2 reply:\n", d_en2["reply"])
assert d_en2["relaxed_spec"] == "budget"
assert "exact" in d_en2["reply"].lower()

print("\n==============================================")
print("  ALL API ENDPOINTS & FLOWS VERIFIED 100%!   ")
print("==============================================")
