#!/usr/bin/env python3
"""
Generate Label Studio API token for testing.
This script will:
1. Create admin user if not exists
2. Generate API token
"""
import urllib.request
import json
import sys

LS_URL = "http://localhost:8080"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "password"

def api_call(method, endpoint, data=None, token=None):
    """Make API call to Label Studio"""
    url = f"{LS_URL}/api{endpoint}"
    headers = {
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Token {token}"
    
    req_data = None
    if data:
        req_data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        response = urllib.request.urlopen(req)
        return json.loads(response.read().decode()), None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_data = json.loads(error_body)
        except Exception:
            error_data = error_body
        return None, (e.code, error_data)
    except Exception as e:
        return None, str(e)

def get_auth_token(username, password):
    """Login and get auth token"""
    print(f"[*] Attempting to login as {username}...")
    data, error = api_call("POST", "/user/login", {
        "username": username,
        "password": password
    })
    
    if error:
        print(f"[!] Login failed: {error}")
        return None
    
    if data and "token" in data:
        token = data["token"]
        print(f"[OK] Got auth token: {token[:10]}...")
        return token
    
    print(f"[!] No token in response: {data}")
    return None

def get_api_token(auth_token):
    """Get or create API token using auth token"""
    print("[*] Getting API token...")
    data, error = api_call("GET", "/user", token=auth_token)
    
    if error:
        print(f"[!] Failed to get user info: {error}")
        return None
    
    if data and "token" in data:
        api_token = data["token"]
        print(f"[OK] Got API token: {api_token[:20]}...")
        return api_token
    
    print(f"[!] No API token in response: {data}")
    return None

def main():
    print("=" * 60)
    print("Label Studio API Token Generator")
    print("=" * 60)
    
    # First, try to login
    auth_token = get_auth_token(ADMIN_USER, ADMIN_PASSWORD)
    if not auth_token:
        print("\n[!] Could not login with admin credentials")
        print("[*] Try manual steps:")
        print("    1. Go to http://localhost:8080/user/account")
        print("    2. Create/copy your API token")
        print("    3. Set LABEL_STUDIO_API_KEY in backend/.env")
        sys.exit(1)
    
    api_token = get_api_token(auth_token)
    if not api_token:
        print("\n[!] Could not get API token")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("SUCCESS!")
    print("=" * 60)
    print("\nAdd this to backend/.env:")
    print(f"  LABEL_STUDIO_API_KEY=\"{api_token}\"")
    print("\nOr replace existing LABEL_STUDIO_API_KEY value with:")
    print(f"  {api_token}")
    print("=" * 60)

if __name__ == "__main__":
    main()
