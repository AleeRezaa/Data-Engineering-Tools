from os import environ, getenv
from ssl import CERT_NONE

from dotenv import load_dotenv
from flask_appbuilder.security.manager import AUTH_DB, AUTH_LDAP
from ldap3 import Tls

load_dotenv()

# Database Configuration
SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{getenv('DATABASE_USER')}:{getenv('DATABASE_PASSWORD')}@{getenv('DATABASE_HOST')}:{getenv('DATABASE_PORT')}/{getenv('DATABASE_DB')}"

# LDAP Configuration
AUTH_TYPE = AUTH_LDAP  # AUTH_LDAP / AUTH_DB
AUTH_USER_REGISTRATION = True
AUTH_USER_REGISTRATION_ROLE = "Gamma"
AUTH_LDAP_SERVER = getenv("AUTH_LDAP_SERVER")
AUTH_LDAP_USE_TLS = False
AUTH_LDAP_BIND_USER = getenv("AUTH_LDAP_BIND_USER")
AUTH_LDAP_BIND_PASSWORD = getenv("AUTH_LDAP_BIND_PASSWORD")
AUTH_LDAP_SEARCH = "OU=Individuals,OU=Mofid,OU=Domain Users,DC=emofid,DC=com"
AUTH_LDAP_UID_FIELD = "sAMAccountName"
AUTH_LDAP_FIRSTNAME_FIELD = "givenName"
AUTH_LDAP_LASTNAME_FIELD = "sn"
AUTH_LDAP_ALLOW_SELF_SIGNED = True
AUTH_LDAP_APPEND_DOMAIN = False
AUTH_LDAP_TLS_CONFIG = Tls(validate=CERT_NONE)

# Read superset metadata
PREVENT_UNSAFE_DB_CONNECTIONS = False

# Required in Superset 6.x
RECAPTCHA_PUBLIC_KEY = ""
RECAPTCHA_PRIVATE_KEY = ""
