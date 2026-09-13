"""Drain accepted local tasks and attempt uncertain submission reconciliation."""
from apps.config import configured_application


def main():
    application = configured_application()
    while application.work_once():
        pass
    application.reconcile()


if __name__ == "__main__":
    main()
