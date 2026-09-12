"""Public build identity; Docker builds supply immutable build arguments."""
import os

VERSION = '3.0.0'
BUILD_NUMBER = os.getenv('APP_BUILD_NUMBER', 'dev')
BUILD_REVISION = os.getenv('APP_BUILD_REVISION', '')
