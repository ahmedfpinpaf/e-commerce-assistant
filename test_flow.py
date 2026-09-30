from app import chat_with_assistant, ChatRequest

print("=== TEST 1: User says 'Mujhe Dell laptop chahiye' ===")
req1 = ChatRequest(message="Mujhe Dell laptop chahiye")
res1 = chat_with_assistant(req1)
print("Bot reply:\n", res1["reply"])
print("Products count:", len(res1["products"]))
print("Stage:", res1["stage"])
print("State:", res1["state"])

print("\n=== TEST 2: User provides specs 'i7, 16GB RAM, 512GB SSD, budget 150000 PKR' ===")
req2 = ChatRequest(
    message="i7, 16GB RAM, 512GB SSD, budget 150000 PKR",
    state=res1["state"]
)
res2 = chat_with_assistant(req2)
print("Bot reply:\n", res2["reply"])
print("Is exact match:", res2["is_exact_match"])
print("Relaxed spec:", res2["relaxed_spec"])
print("Model used:", res2["model_used"])
print("Products returned:")
for p in res2["products"]:
    print(f" - {p.get('title')} | Brand: {p.get('brand')} | Price: ${p.get('price')} USD (~Rs {p.get('price_pkr'):,} PKR)")

print("\n=== TEST 3: User says 'Mujhe mobile chahiye' -> 'Samsung, budget 150000 PKR' ===")
req3a = ChatRequest(message="Mujhe mobile chahiye")
res3a = chat_with_assistant(req3a)
print("Bot ask specs:\n", res3a["reply"])

req3b = ChatRequest(message="Samsung, budget 150000 PKR", state=res3a["state"])
res3b = chat_with_assistant(req3b)
print("Bot reply:\n", res3b["reply"])
print("Is exact match:", res3b["is_exact_match"])
for p in res3b["products"]:
    print(f" - {p.get('title')} | Price: ${p.get('price')} USD (~Rs {p.get('price_pkr'):,} PKR)")

print("\n=== ALL UNIT TESTS COMPLETED SUCCESSFULLY ===")
