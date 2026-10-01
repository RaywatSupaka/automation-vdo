"""Versioned account binding; distinguish user selection from a live UI read."""
import math
from core.shopee_posting.progress import ACTIVE


def flow_version(row):
    version = (row.get('run_contract') or {}).get('posting_flow_version', 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError('รุ่นขั้นตอนโพสต์ไม่รองรับ • ยังไม่ส่งโพสต์')
    return version


def account_check_mode(row):
    mode = (row.get('run_contract') or {}).get('account_check_mode', 'live_ui')
    if mode not in ('live_ui', 'confirmed_selection'):
        raise ValueError('รูปแบบการยืนยันคิวไม่รองรับ • ยังไม่ส่งโพสต์')
    return mode


def confirmed_selection(run, account, device_id):
    confirmation = run.get('start_confirmation') or {}
    at = confirmation.get('confirmed_at')
    if (run.get('account_check_mode') != 'confirmed_selection'
            or confirmation.get('run_id') != run.get('id')
            or confirmation.get('account') != account or confirmation.get('device_id') != device_id
            or type(at) not in (int, float) or not math.isfinite(at)
            or not run.get('started_at', float('inf')) <= at):
        raise ValueError('ยังไม่มีการยืนยันเริ่มคิวนี้ • ไม่ใช้การยืนยันจากรอบเก่า')
    return dict(confirmation)


def queue_account(state, row, account, device_id):
    run = state.get('posting_run') or {}
    proof = run.get('account_receipt') or {}
    contract = row.get('run_contract') or {}
    mode = account_check_mode(row)
    proof_at = proof.get('confirmed_at' if mode == 'confirmed_selection' else 'verified_at')
    if (flow_version(row) != 2 or run.get('status') not in ACTIVE
            or not run.get('id') or row.get('posting_run_id') != run['id']
            or row['id'] not in run.get('ids', [])
            or proof.get('run_id') != run['id'] or run.get('account') != account
            or proof.get('account') != account or contract.get('account') != account
            or proof.get('device_id') != device_id or contract.get('device_id') != device_id
            or not account or not device_id
            or proof.get('source', 'live_ui') != mode
            or type(proof_at) not in (int, float)
            or not math.isfinite(proof_at)
            or not run.get('started_at', float('inf')) <= proof_at):
        raise ValueError('ยังยืนยันบัญชีและมือถือของคิวรอบนี้ไม่ได้ • ไม่ใช้หลักฐานจากคิวเก่า')
    if mode == 'confirmed_selection' and proof_at != confirmed_selection(run, account, device_id)['confirmed_at']:
        raise ValueError('การยืนยันไม่ตรงกับการกดเริ่มคิวนี้ • ไม่ส่งโพสต์')
    return dict(proof)
