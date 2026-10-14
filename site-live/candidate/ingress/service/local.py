"""File-based local operator for the same Store; never executes a native request."""
import argparse
import json
from pathlib import Path
from store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('intake','awaiting','prepare','submit','claim','complete','fail','get'))
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--runtime', type=Path, default=Path(__file__).with_name('runtime.unverified.json'))
    parser.add_argument('--input', type=Path)
    parser.add_argument('--task-id')
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        store = Store(args.database, json.loads(args.runtime.read_text(encoding='utf-8')))
        data = json.loads(args.input.read_text(encoding='utf-8')) if args.input else None
        if args.action == 'get':
            result = store.get(args.task_id)
        elif args.action == 'awaiting':
            result = store.awaiting()
        elif args.action == 'intake':
            result = store.intake(data)
        elif args.action == 'prepare':
            if not isinstance(data,dict) or set(data) not in (
                    {'task_id','role','assessment'}, {'task_id','role','assessment','logic_validation_required'}):
                raise ValueError('Internal prepare requires task_id, role and assessment')
            result = store.prepare(**data)
        elif args.action == 'submit':
            result = store.submit(data)
        elif args.action == 'claim':
            if not isinstance(data, dict) or set(data) != {'worker_id'}:
                raise ValueError('Claim input requires worker_id only')
            result = store.claim(**data)
        else:
            if not isinstance(data, dict):
                raise ValueError('Completion/failure object required')
            expected = {'task_id','lease_token','output','receipt'} if args.action == 'complete' else {'task_id','lease_token','reason'}
            if set(data) != expected:
                raise ValueError('Invalid completion/failure fields')
            result = getattr(store, args.action)(**data)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({'action':args.action,'state':result.get('state') if result else 'empty_queue',
                          'task_id':result.get('task_id') if result else None,'saved_to':str(args.out)},ensure_ascii=False))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__':
    main()
