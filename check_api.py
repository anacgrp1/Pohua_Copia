import subprocess
import time
import requests
import sys

# Start the uvicorn server in the background
process = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--port", "8002"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(3) # Wait for it to start

try:
    response = requests.post(
        "http://localhost:8002/api/auth/login",
        json={"correo": "sales.isc@cgr-international.com", "password": "password123"}
    )
    print("STATUS:", response.status_code)
    print("JSON:", response.json())
except Exception as e:
    print("Error connecting:", e)

# Terminate the server
process.terminate()
stdout, stderr = process.communicate()
print("\n--- STDOUT ---")
print(stdout.decode())
print("\n--- STDERR ---")
print(stderr.decode())
