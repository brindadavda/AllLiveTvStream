import certifi
from pymongo import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://davdabrinda_db_user:MGl9sD2Q93jCBybL@cluster0.uo1byzk.mongodb.net/?appName=Cluster0"

print("Connecting to MongoDB Atlas Cluster0...")
# Create a new client and connect to the server
client = MongoClient(
    uri,
    server_api=ServerApi('1'),
    tlsCAFile=certifi.where(),
    tls=True,
    tlsAllowInvalidCertificates=True
)

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("\n[SUCCESS] Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print("\n[ERROR] Connection failed. This is most likely due to:")
    print("1. Your current network IP address is not whitelisted in MongoDB Atlas.")
    print("   -> Go to MongoDB Atlas Console -> Network Access -> Add IP Address -> 'Allow Access From Anywhere (0.0.0.0/0)'")
    print("2. System OpenSSL mismatches on macOS (solved by using certifi).")
    print(f"\nExact Exception: {e}")
