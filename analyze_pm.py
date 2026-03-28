import json
import sys

with open('postman_collection.json', 'r') as f:
    coll = json.load(f)

def extract_requests(item_list, path=""):
    results = []
    for item in item_list:
        if "request" in item:
            results.append({
                "name": item.get("name"),
                "method": item["request"]["method"],
                "url": item["request"]["url"]["raw"] if isinstance(item["request"]["url"], dict) else item["request"]["url"],
                "body": item["request"].get("body", {}).get("raw", "")
            })
        if "item" in item:
            results.extend(extract_requests(item["item"], path + " / " + item.get("name", "")))
    return results

reqs = extract_requests(coll.get("item", []))

print(f"Total requests: {len(reqs)}")
for r in reqs:
    b = r['body']
    has_body = bool(b and b.strip() and b.strip() != "{}")
    print(f"[{r['method']}] {r['url']} - HasBody: {has_body}")
    if has_body:
        snippet = b[:100].replace('\n', ' ')
        print(f"   Body snippet: {snippet}")

