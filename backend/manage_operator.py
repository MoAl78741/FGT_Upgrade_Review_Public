"""Provision/recover the public operator locally; password never appears in arguments."""
import argparse,getpass,re
from .database import SessionLocal,engine,run_migrations
from .models import Base,OperatorUser,OperatorSession
from .team import hash_password

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--username',default='admin');args=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_.@-]{1,80}',args.username):p.error('Invalid username.')
    password=getpass.getpass('Operator password (14–256 characters): ')
    if not 14<=len(password)<=256 or password!=getpass.getpass('Confirm password: '):p.error('Passwords must match and contain 14–256 characters.')
    run_migrations();Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user=db.query(OperatorUser).filter_by(username=args.username.lower()).first()
        if not user:user=OperatorUser(username=args.username.lower());db.add(user)
        user.password_hash=hash_password(password);user.must_change_password=True
        db.query(OperatorSession).delete();db.commit()
    print('Operator provisioned. Sign in at /administration and change the initial password.')
if __name__=='__main__':main()
