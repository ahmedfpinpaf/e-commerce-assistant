from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

print("===================================================================")
print("TEST 1: Non-existent category lock: 'I need a car.'")
print("===================================================================")
r1 = client.post("/api/chat", json={"message": "I need a car."})
d1 = r1.json()
print("Reply:\n", d1["reply"])
print("Products count:", len(d1["products"]))
assert r1.status_code == 200
assert len(d1["products"]) == 0
assert "couldn't find a car in the catalog" in d1["reply"].lower()
print("--> TEST 1 PASSED: Non-existent category car strictly rejected with 0 products!\n")


print("===================================================================")
print("TEST 2: Non-existent category lock: 'Show me a television.'")
print("===================================================================")
r2 = client.post("/api/chat", json={"message": "Show me a television."})
d2 = r2.json()
print("Reply:\n", d2["reply"])
print("Products count:", len(d2["products"]))
assert r2.status_code == 200
assert len(d2["products"]) == 0
assert "couldn't find a television in the catalog" in d2["reply"].lower()
print("--> TEST 2 PASSED: Non-existent category television strictly rejected with 0 products!\n")


print("===================================================================")
print("TEST 3: Non-existent category lock: 'Show me a camera.'")
print("===================================================================")
r3 = client.post("/api/chat", json={"message": "Show me a camera."})
d3 = r3.json()
print("Reply:\n", d3["reply"])
print("Products count:", len(d3["products"]))
assert r3.status_code == 200
assert len(d3["products"]) == 0
assert "couldn't find a camera in the catalog" in d3["reply"].lower()
print("--> TEST 3 PASSED: Non-existent category camera strictly rejected with 0 products!\n")


print("===================================================================")
print("TEST 4: Spec Asking before search: 'I need a smartphone.'")
print("===================================================================")
r4 = client.post("/api/chat", json={"message": "I need a smartphone."})
d4 = r4.json()
print("Reply:\n", d4["reply"])
print("Products count:", len(d4["products"]))
assert r4.status_code == 200
assert len(d4["products"]) == 0
assert "what specifications are important to you" in d4["reply"].lower()
assert "budget" in d4["reply"].lower()
print("--> TEST 4 PASSED: Spec asking prompt returned before search!\n")


print("===================================================================")
print("TEST 5: Unmatched specs (No Silent Relaxation): 'I want a smartphone with 12GB RAM and 512GB storage.'")
print("===================================================================")
r5 = client.post("/api/chat", json={"message": "I want a smartphone with 12GB RAM and 512GB storage."})
d5 = r5.json()
print("Reply:\n", d5["reply"])
print("Products count:", len(d5["products"]))
assert r5.status_code == 200
assert len(d5["products"]) == 0
assert "couldn't find a smartphone matching all of those specifications" in d5["reply"].lower()
assert "change one of the requirements" in d5["reply"].lower()
print("--> TEST 5 PASSED: Unmatched specs returned strict prompt without silent relaxation!\n")


print("===================================================================")
print("TEST 6: Unmatched processor: 'Show me one smartphone with 8GB RAM, 256GB storage and Snapdragon processor.'")
print("===================================================================")
r6 = client.post("/api/chat", json={"message": "Show me one smartphone with 8GB RAM, 256GB storage and Snapdragon processor."})
d6 = r6.json()
print("Reply:\n", d6["reply"])
print("Products count:", len(d6["products"]))
assert r6.status_code == 200
assert len(d6["products"]) == 0
assert "couldn't find a smartphone matching all of those specifications" in d6["reply"].lower()
print("--> TEST 6 PASSED: Snapdragon smartphone strictly rejected with 0 products!\n")


print("===================================================================")
print("TEST 7: Unmatched budget: 'Show me one laptop under $1000'")
print("===================================================================")
r7 = client.post("/api/chat", json={"message": "Show me one laptop under $1000"})
d7 = r7.json()
print("Reply:\n", d7["reply"])
print("Products count:", len(d7["products"]))
assert r7.status_code == 200
assert len(d7["products"]) == 0
assert "couldn't find a laptop matching all of those specifications" in d7["reply"].lower()
print("--> TEST 7 PASSED: Laptop under $1000 rejected without relaxation!\n")


print("===================================================================")
print("TEST 8: Matched budget: 'Show me one smartphone under $500'")
print("===================================================================")
r8 = client.post("/api/chat", json={"message": "Show me one smartphone under $500"})
d8 = r8.json()
print("Reply:\n", d8["reply"])
print("Products count:", len(d8["products"]))
assert r8.status_code == 200
assert len(d8["products"]) == 1
assert d8["products"][0]["title"] == "Samsung Galaxy S8"
# Rule 12 template checks
assert "I found one product matching your requirements:" in d8["reply"]
assert "Product: Samsung Galaxy S8" in d8["reply"]
assert "Brand: Samsung" in d8["reply"]
assert "Model:" in d8["reply"]
assert "Price:" in d8["reply"]
assert "Specifications:" in d8["reply"]
assert "- Category: smartphones" in d8["reply"]
print("--> TEST 8 PASSED: Exactly 1 product returned in exact Rule 12 format!\n")


print("===================================================================")
print("TEST 9: Matched brand: 'Show me one Dell laptop'")
print("===================================================================")
r9 = client.post("/api/chat", json={"message": "Show me one Dell laptop"})
d9 = r9.json()
print("Reply:\n", d9["reply"])
print("Products count:", len(d9["products"]))
assert r9.status_code == 200
assert len(d9["products"]) == 1
assert d9["products"][0]["brand"].lower() == "dell"
assert d9["products"][0]["title"] == "New DELL XPS 13 9300 Laptop"
assert "Product: New DELL XPS 13 9300 Laptop" in d9["reply"]
print("--> TEST 9 PASSED: Exactly 1 Dell laptop returned!\n")


print("===================================================================")
print("TEST 10: Roman Urdu query: 'Mujhe ek smartphone chahiye budget $500'")
print("===================================================================")
r10 = client.post("/api/chat", json={"message": "Mujhe ek smartphone chahiye budget $500"})
d10 = r10.json()
print("Reply:\n", d10["reply"])
print("Products count:", len(d10["products"]))
assert r10.status_code == 200
assert len(d10["products"]) == 1
assert "Product: Samsung Galaxy S8" in d10["reply"]
print("--> TEST 10 PASSED: Roman Urdu query returned exactly 1 product!\n")


print("===================================================================")
print("TEST 11: Multi-turn flow: Ask category -> Ask specs -> Provide budget")
print("===================================================================")
turn_a = client.post("/api/chat", json={"message": "I want a laptop"})
data_a = turn_a.json()
assert len(data_a["products"]) == 0
assert data_a["stage"] == "COLLECTING_SPECS"

turn_b = client.post("/api/chat", json={
    "message": "Dell with budget $1600",
    "state": data_a["state"]
})
data_b = turn_b.json()
assert len(data_b["products"]) == 1
assert data_b["products"][0]["title"] == "New DELL XPS 13 9300 Laptop"
print("--> TEST 11 PASSED: Multi-turn conversation works seamlessly!\n")


print("===================================================================")
print("  ALL 11 STRICT CATALOG PRODUCT ASSISTANT TESTS PASSED 100%!       ")
print("===================================================================")
