import traceback
try:
    import optuna
    print('optuna', optuna.__version__)
except Exception:
    traceback.print_exc()
    raise
