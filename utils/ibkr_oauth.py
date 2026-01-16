import os
import json
import base64
import secrets
import binascii
import requests
import time
import datetime
from urllib.parse import quote_plus

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import HMAC
from cryptography.hazmat.backends import default_backend

class IBKRAuthClient:
    """
    Client for IBKR OAuth 1.0a Authentication.
    Handles Request Token, Access Token, and Live Session Token generation.
    """
    def __init__(self, config):
        self.consumer_key = config['CONSUMER_KEY']
        self.base_url = config['BASE_URL'] # e.g., https://api.ibkr.com/v1/api
        
        # Load keys once at initialization
        self.signature_key = self._load_rsa_key(config['SIGNATURE_KEY_PATH'])
        self.private_encryption_key = self._load_rsa_key(config['PRIVATE_ENCRYPTION_PATH'])
        self.dh_params = self._load_dh_params(config['DH_PARAM_PATH'])
        
        self.realm = "test_realm" if "TESTCONS" in self.consumer_key else "limited_poa"
        
        # Intermediate tokens
        self.request_token = None
        self.access_token = None
        self.access_secret = None
        self.live_session_token = None

    def _load_rsa_key(self, path):
        """Load an RSA private key from a PEM file."""
        with open(path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )
        return private_key

    def _load_dh_params(self, path):
        """
        Load DH parameters (Prime and Generator) from a PEM file.
        Note: According to docs, Generator is always 2.
        """
        from cryptography.hazmat.primitives.asymmetric import dh
        from cryptography.hazmat.primitives import serialization
        
        with open(path, "rb") as f:
            parameters = serialization.load_pem_parameters(f.read())
            # Generator is always 2 according to docs
            return {
                'p': int.from_bytes(parameters.parameter_numbers('p')),
                'g': int.from_bytes(parameters.parameter_numbers('g')) 
            }

    def _generate_oauth_nonce(self):
        """Generate a random 128-bit hex string for oauth_nonce."""
        return secrets.token_hex(16)[2:]

    def _get_oauth_timestamp(self):
        """Get current Unix timestamp in seconds."""
        return str(int(time.time()))

    def _generate_rsa_signature(self, base_string):
        """
        Sign the base string using RSA-SHA256 with PKCS1v1.5 padding.
        """
        signature = self.signature_key.sign(
            padding.PKCS1v1_5(),
            hashes.SHA256(),
            base_string.encode('utf-8')
        )
        return base64.b64encode(signature).decode('utf-8')

    def _build_oauth_params(self, additional_params=None):
        """
        Build the core OAuth parameter dictionary.
        """
        params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_nonce": self._generate_oauth_nonce(),
            "oauth_signature_method": "RSA-SHA256",
            "oauth_timestamp": self._get_oauth_timestamp(),
            "realm": self.realm
        }
        if additional_params:
            params.update(additional_params)
        return params

    def _format_oauth_header(self, params):
        """
        Format the Authorization header string.
        """
        sorted_params = sorted(params.items())
        param_str = ", ".join([f'{k}="{v}"' for k, v in sorted_params])
        return f"OAuth {param_str}"

    def _get_request_token(self):
        """
        Step 1: Request Token.
        Endpoint: /oauth/request_token
        """
        url = f"{self.base_url}/oauth/request_token"
        
        # oauth_callback is required. "oob" is out-of-band.
        params = self._build_oauth_params({
            "oauth_callback": "oob"
        })
        
        # Construct Base String: METHOD&URL&SORTED_PARAMS
        # URL and params must be RFC3986-encoded (quote_plus)
        method = "POST"
        encoded_url = quote_plus(url)
        param_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in sorted(params.items())])
        base_string = f"{method}&{encoded_url}&{param_string}"
        
        # Sign the base string
        signature = self._generate_rsa_signature(base_string)
        params["oauth_signature"] = quote_plus(signature)
        
        headers = {
            "Authorization": self._format_oauth_header(params),
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "python/3.8"
        }
        
        # Make the request
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return response.json()['oauth_token']

    def _get_access_token(self, verifier):
        """
        Step 3: Access Token.
        Endpoint: /oauth/access_token
        Requires the Request Token and the Verifier from the user login.
        """
        url = f"{self.base_url}/oauth/access_token"
        
        params = self._build_oauth_params({
            "oauth_token": self.request_token,
            "oauth_verifier": verifier
        })
        
        # Construct Base String
        method = "POST"
        encoded_url = quote_plus(url)
        param_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in sorted(params.items())])
        base_string = f"{method}&{encoded_url}&{param_string}"
        
        # Sign the base string
        signature = self._generate_rsa_signature(base_string)
        params["oauth_signature"] = quote_plus(signature)
        
        headers = {
            "Authorization": self._format_oauth_header(params),
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "python/3.8"
        }
        
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        self.access_token = data['oauth_token']
        self.access_secret = data['oauth_token_secret']
        return self.access_token, self.access_secret

    def _decrypt_access_secret(self):
        """
        Decrypt the access_token_secret using the private_encryption_key.
        The secret is an RSA-encrypted byte string of the DH Private Key's X value.
        Returns the hex string representation of the decrypted X (prepend).
        """
        # Base64 decode the secret
        encrypted_secret_bytes = base64.b64decode(self.access_secret)
        
        # Decrypt using PKCS1v1.5 padding
        decrypted_secret_bytes = self.private_encryption_key.decrypt(
            padding.PKCS1v1_5(),
            encrypted_secret_bytes
        )
        
        # Convert to hex string for use in base string and K calculation
        prepend_hex = decrypted_secret_bytes.hex()
        return prepend_hex

    def _get_live_session_token(self):
        """
        Step 4: Live Session Token (LST).
        Endpoint: /oauth/live_session_token
        
        This involves:
        1. Generating a Diffie-Hellman challenge.
        2. Decrypting the access_secret to get the "prepend" value.
        3. Building the request base string (prepend + method + url + params).
        4. Sending the request and receiving B, lst_sig.
        5. Calculating K from B.
        6. Computing the final LST using HMAC-SHA1.
        """
        url = f"{self.base_url}/oauth/live_session_token"
        
        # 1. Diffie-Hellman Challenge
        # Generate a random 256-bit integer
        dh_random = secrets.randbits(256)
        
        # B = g ^ a % p
        g = 2 # Always 2 according to docs
        p = self.dh_params['p']
        dh_challenge = pow(g, dh_random, p)
        # Remove leading '0x' and ensure it's a valid hex string
        dh_challenge_hex = format(dh_challenge, 'x')[2:]
        
        # 2. Prepend
        prepend_hex = self._decrypt_access_secret()
        
        # Build params for the request
        params = self._build_oauth_params({
            "oauth_token": self.access_token,
            "diffie_hellman_challenge": dh_challenge_hex
        })
        
        # 3. Base String Construction: PREPEND + METHOD&URL&PARAMS
        # The prepend_hex string is prepended to the base string.
        # It must be URL-encoded (quote_plus) as part of the base string.
        method = "POST"
        encoded_url = quote_plus(url)
        param_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in sorted(params.items())])
        
        # Note: The documentation says "PUT prepend at beginning of base string".
        # Base string format: PREPEND&METHOD&URL&PARAMS
        # The PREPEND must also be URL-encoded.
        base_string = f"{prepend_hex}&{method}&{encoded_url}&{param_string}"
        
        # 4. Sign the request base string
        signature = self._generate_rsa_signature(base_string)
        params["oauth_signature"] = quote_plus(signature)
        
        headers = {
            "Authorization": self._format_oauth_header(params),
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "python/3.8"
        }
        
        # Send the request
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        B_hex = data['diffie_hellman_response'] # The server's B value
        lst_sig = data['live_session_token_signature'] # For validation
        lst_exp = data['live_session_token_expiration']
        
        # 5. Calculate K = B ^ a % p
        # Reuse the same dh_random (a) and dh_params (p)
        # B needs to be converted from hex string to int
        # Handle potential sign bit and odd-length hex strings
        if B_hex[0] not in '0123456789ABCDEF':
            B_hex = '0' + B_hex
        
        B = int(B_hex, 16)
        K = pow(B, dh_random, p)
        
        # 6. Compute the Live Session Token (LST)
        # Convert K to hex string, then to bytes.
        # Handle leading sign bit and odd-length hex strings.
        K_hex = format(K, 'x')[2:]
        if len(K_hex) % 2 != 0:
             # Add a leading 0 if odd number of chars
            K_hex = "0" + K_hex
        # If lacking sign bit (len(bin(K)[2:]) % 8 == 0), prepend a null byte
        if bin(K).count('1') % 8 == 0:
            K_hex = "00" + K_hex
            
        K_bytes = bytes.fromhex(K_hex)
        
        # The prepend is the decrypted access_secret, which we need as bytes.
        # The prepend_hex is the hex string, convert to bytes.
        prepend_bytes = bytes.fromhex(prepend_hex)
        
        # LST = HMAC-SHA1(Key=K_bytes, Message=prepend_bytes)
        h = HMAC.new(K_bytes, hashes.SHA1(), digestmod=hashes.SHA1())
        h.update(prepend_bytes)
        lst_hash_bytes = h.digest()
        
        # Base64 encode the hash to get the final LST string
        self.live_session_token = base64.b64encode(lst_hash_bytes).decode('utf-8')
        
        # Optional: Validate the computed LST
        # Re-hash consumer key using computed LST
        validation_h = HMAC.new(base64.b64decode(self.live_session_token), hashes.SHA1(), digest=self.consumer_key.encode('utf-8')).digest()
        if validation_h.hex() != lst_sig:
            print("WARNING: LST validation failed. Check implementation.")
            print(f"Expected: {lst_sig}")
            print(f"Computed: {validation_h.hex()}")
        else:
            print("LST validated successfully.")
            
        print(f"Live Session Token Generated Successfully. Expires: {datetime.fromtimestamp(lst_exp)}")
        return self.live_session_token

    def make_authenticated_request(self, method, endpoint, body=None):
        """
        Generic method to make an authenticated request using the Live Session Token.
        Uses HMAC-SHA256 for signing.
        """
        url = f"{self.base_url}{endpoint}"
        
        # Construct OAuth params (note: HMAC-SHA256 for signature method)
        params = self._build_oauth_params({
            "oauth_token": self.live_session_token,
            "oauth_signature_method": "HMAC-SHA256"
        })
        
        # Construct Base String for signing
        method_upper = method.upper()
        encoded_url = quote_plus(url)
        param_string = "&".join([f"{k}={quote_plus(str(v))}" for k, v in sorted(params.items())])
        base_string = f"{method_upper}&{encoded_url}&{param_string}"
        
        # Sign with HMAC-SHA256. The key is the LST (decoded to bytes).
        lst_bytes = base64.b64decode(self.live_session_token)
        h = HMAC.new(lst_bytes, hashes.SHA256(), digestmod=hashes.SHA256())
        h.update(base_string.encode('utf-8'))
        signature = base64.b64encode(h.digest()).decode('utf-8')
        
        params["oauth_signature"] = quote_plus(signature)
        
        headers = {
            "Authorization": self._format_oauth_header(params),
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": "python/3.8"
        }
        
        if method_upper == "GET":
            response = requests.get(url, headers=headers)
        else:
            response = requests.post(url, headers=headers, json=body)
            
        response.raise_for_status()
        return response.json()

# --- Usage Example ---
if __name__ == "__main__":
    # Configuration
    # IMPORTANT: Replace these paths and keys with your actual values.
    # The DH param file must contain 'p' (prime) and 'g' (generator, always 2).
    # The signature key is for signing the initial OAuth requests.
    # The private_encryption key is for decrypting the access_token_secret.
    config = {
        'CONSUMER_KEY': 'TESTCONS', # Your Consumer Key
        'BASE_URL': 'https://api.ibkr.com/v1/api',
        'SIGNATURE_KEY_PATH': 'signature_key.pem', # Path to RSA private key
        'PRIVATE_ENCRYPTION_PATH': 'private_encryption.pem', # Path to RSA private key
        'DH_PARAM_PATH': 'dhparam.pem' # Path to DH parameters file
    }

    client = IBKRAuthClient(config)

    print("--- Step 1: Request Token ---")
    try:
        request_token = client.request_token()
        print(f"Request Token obtained: {request_token}")
    except Exception as e:
        print(f"Error obtaining Request Token: {e}")
        exit()
    
    print("\n--- Step 2: Authorization (Manual) ---")
    # In a real application, you would redirect the user to:
    # https://interactivebrokers.com/authorize?oauth_token=<REQUEST_TOKEN>
    # The user logs in, and your callback URL receives the oauth_verifier.
    # For this script, we simulate this step by asking for input.
    print("Please visit the following URL to authorize the application:")
    print(f"https://interactivebrokers.com/authorize?oauth_token={request_token}")
    verifier = input("Enter the 'oauth_verifier' value from the callback URL: ")

    print("\n--- Step 3: Access Token ---")
    try:
        access_token, access_secret = client.get_access_token(verifier)
        print(f"Access Token obtained: {access_token}")
        # print(f"Access Secret: {access_secret}")
    except Exception as e:
        print(f"Error obtaining Access Token: {e}")
        exit()

    print("\n--- Step 4: Live Session Token (LST) ---")
    try:
        lst = client.get_live_session_token()
        print(f"Live Session Token (LST): {lst}")
    except Exception as e:
        print(f"Error obtaining LST: {e}")
        exit()
    
    print("\n--- Step 5: Authenticated Request Example ---")
    # Example: Initialize brokerage session
    init_endpoint = "/iserver/auth/ssodh/init"
    body = {"publish": True, "compete": True}
    
    try:
        response = client.make_authenticated_request("POST", init_endpoint, body)
        print(f"Brokerage Session Init Response: {json.dumps(response, indent=2)}")
        print("\nYou can now use the generated LST to make authenticated API requests.")
    except Exception as e:
        print(f"Authenticated request failed: {e}")

