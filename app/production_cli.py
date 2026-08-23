"""Production administration CLI.

Examples:
  python -m app.production_cli preflight
  python -m app.production_cli migrate
  python -m app.production_cli upgrade-check --from-version 2.9.0
  python -m app.production_cli backup --destination /backup/app.tar.gz
"""
from __future__ import annotations
import argparse, json
from .persistence import get_repository
from .production_runtime import ProductionConfigValidator, MigrationManager, BackupManager, UpgradeAdvisor


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='cmd',required=True)
    sub.add_parser('preflight'); sub.add_parser('migrate')
    up=sub.add_parser('upgrade-check'); up.add_argument('--from-version',default='')
    bk=sub.add_parser('backup'); bk.add_argument('--destination',default='')
    ins=sub.add_parser('backup-inspect'); ins.add_argument('path')
    args=parser.parse_args(); repo=get_repository(); validator=ProductionConfigValidator(); migrations=MigrationManager(repo); backups=BackupManager(repo)
    if args.cmd=='preflight': out={'configuration':validator.validate(),'migrations':migrations.status()}
    elif args.cmd=='migrate': out=migrations.migrate(actor='production_cli')
    elif args.cmd=='upgrade-check': out=UpgradeAdvisor(migrations,validator).check(args.from_version)
    elif args.cmd=='backup': out=backups.create(args.destination or None)
    else: out=backups.inspect(args.path)
    print(json.dumps(out,ensure_ascii=False,indent=2))
    if args.cmd=='preflight' and (out['configuration']['status']!='ok'): raise SystemExit(2)

if __name__=='__main__': main()
