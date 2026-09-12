#!/usr/bin/env python3
"""Generate a dedicated edition proxy configuration; never change host trust stores."""
import argparse,json
from pathlib import Path
from urllib.parse import urlsplit
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--origin',required=True);args=p.parse_args()
u=urlsplit(args.origin)
if u.scheme!='https' or not u.hostname or u.path or u.query or u.fragment or u.username:p.error('Use an exact HTTPS origin with no path, credentials or query.')
config={'admin':{'listen':'0.0.0.0:2019'},'apps':{'http':{'servers':{'site':{'listen':[':8443'],
 'automatic_https':{'disable_redirects':True},'tls_connection_policies':[{}],
 'routes':[{'match':[{'host':[u.hostname]}],'handle':[{'handler':'reverse_proxy','upstreams':[{'dial':'fgt-upgrade:8000'}]}]}]}}},
 'tls':{'automation':{'policies':[{'subjects':[u.hostname],'issuers':[{'module':'internal'}]}]}}}}
dest=Path('deployment/caddy.json');dest.write_text(json.dumps(config,indent=2)+'\n')
print(f'Wrote {dest}. Set APP_ORIGIN/PUBLIC_ORIGIN={args.origin} and TLS_PORT={u.port or 443} in .env. Use compose.administration.yml. Device certificate trust remains your choice.')
