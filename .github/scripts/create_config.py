"""Copy to .github/scripts/create_config.py

Writes the Snowflake CLI connection used by the deploy workflow. Only `database`
and `schema` need changing per app.
"""
import os

account = os.environ['SF_ACCOUNT']
user = os.environ['SF_USER']
role = os.environ['SF_ROLE']
warehouse = os.environ['SF_WAREHOUSE']

config = f"""[connections.default]
account = "{account}"
user = "{user}"
authenticator = "SNOWFLAKE_JWT"
private_key_path = "/tmp/snowflake_key.p8"
role = "{role}"
warehouse = "{warehouse}"
database = "STREAMLIT_APPS"
schema = "DATA_MANAGEMENT"
"""

os.makedirs(os.path.expanduser("~/.snowflake"), exist_ok=True)
with open(os.path.expanduser("~/.snowflake/config.toml"), "w") as f:
    f.write(config)

print("Config written successfully")
