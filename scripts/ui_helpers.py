"""Shared UI setup for no-cost browser regressions."""


def accept_adult_consent(scope):
    """Skip the intro, then explicitly accept when this tab has not yet done so."""
    scope.get_by_test_id("splash-screen").wait_for(timeout=20000)
    skip = scope.get_by_test_id("skip-intro-btn")
    if skip.count() and skip.is_visible():
        try: skip.click(timeout=1500)
        except Exception: pass  # The auto-ending intro can detach between checks.
    checkbox = scope.get_by_test_id("disclaimer-checkbox")
    if not checkbox.count() and scope.get_by_test_id("splash-login-btn").count():
        return
    checkbox.wait_for(timeout=10000)
    if not checkbox.is_checked(): checkbox.check()
    scope.get_by_test_id("enter-roast-btn").click()


def enter_preview(scope):
    accept_adult_consent(scope)
    scope.get_by_test_id("preview-login-btn").click()
    scope.get_by_test_id("roast-studio").wait_for(timeout=20000)


async def accept_adult_consent_async(scope):
    await scope.get_by_test_id("splash-screen").wait_for(timeout=20000)
    skip = scope.get_by_test_id("skip-intro-btn")
    if await skip.count() and await skip.is_visible():
        try: await skip.click(timeout=1500)
        except Exception: pass  # It may have finished naturally.
    checkbox = scope.get_by_test_id("disclaimer-checkbox")
    if not await checkbox.count() and await scope.get_by_test_id("splash-login-btn").count():
        return
    await checkbox.wait_for(timeout=10000)
    if not await checkbox.is_checked(): await checkbox.check()
    await scope.get_by_test_id("enter-roast-btn").click()
