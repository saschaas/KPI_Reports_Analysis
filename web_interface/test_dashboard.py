#!/usr/bin/env python3
"""
Test dashboard functionality using Playwright.
"""

import sys
import io
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def test_dashboard():
    """Test the dashboard HTML file."""

    dashboard_path = Path(__file__).parent / "dashboard.html"

    if not dashboard_path.exists():
        print(f"❌ Dashboard file not found: {dashboard_path}")
        return False

    print(f"🧪 Testing dashboard: {dashboard_path}")

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        # Collect all console messages
        console_messages = []
        errors = []

        def handle_console(msg):
            message = f"[{msg.type}] {msg.text}"
            console_messages.append(message)
            print(f"   {message}")

        def handle_error(error):
            error_msg = str(error)
            errors.append(error_msg)
            print(f"   ❌ [PAGE ERROR] {error_msg}")

        page.on("console", handle_console)
        page.on("pageerror", handle_error)

        try:
            # Navigate to dashboard
            print("📄 Loading dashboard...")
            page.goto(f"file:///{dashboard_path.absolute()}")

            # Wait for page to load
            page.wait_for_load_state("networkidle", timeout=10000)

            # Check if main elements exist
            print("✅ Page loaded successfully")

            # Check for dashboard header
            header = page.locator("h1:has-text('Analysis Dashboard')")
            if header.count() > 0:
                print("✅ Dashboard header found")
            else:
                print("❌ Dashboard header not found")
                return False

            # Check for metrics cards
            metrics = page.locator(".metric-card")
            metric_count = metrics.count()
            print(f"✅ Found {metric_count} metric cards")

            # Wait a bit for data to load
            print("⏳ Waiting for data to load...")
            page.wait_for_timeout(3000)

            # Check if loading spinner is hidden
            spinner = page.locator("#loadingSpinner")
            spinner_visible = spinner.is_visible()

            if spinner_visible:
                print("⚠️  Loading spinner still visible - data may not have loaded")
            else:
                print("✅ Loading spinner hidden")

            # Check if error message is shown
            error_msg = page.locator("#noDataMessage")
            error_visible = error_msg.is_visible()

            if error_visible:
                error_text = error_msg.inner_text()
                print(f"⚠️  Error message displayed: {error_text[:100]}")
            else:
                print("✅ No error message displayed")

            # Check if reports are displayed
            reports_list = page.locator("#reportsList .report-card")
            report_count = reports_list.count()

            if report_count > 0:
                print(f"✅ Found {report_count} reports displayed")
            else:
                print("⚠️  No reports displayed")

            # Check month selector
            month_selector = page.locator("#monthSelector")
            if month_selector.count() > 0:
                options = month_selector.locator("option")
                option_count = options.count()
                print(f"✅ Month selector has {option_count} options")

            # Take screenshot
            screenshot_path = Path(__file__).parent / "dashboard_test_screenshot.png"
            page.screenshot(path=str(screenshot_path))
            print(f"📸 Screenshot saved: {screenshot_path}")

            # Print console summary
            print(f"\n📊 Console Messages: {len(console_messages)}")
            print(f"❌ Errors: {len(errors)}")

            if errors:
                print("\n⚠️  ERRORS DETECTED:")
                for err in errors:
                    print(f"   {err}")

            # Keep browser open for inspection
            print("\n🔍 Browser will stay open for 10 seconds for inspection...")
            page.wait_for_timeout(10000)

            browser.close()

            if errors:
                print("\n❌ Dashboard test completed with errors")
                return False
            else:
                print("\n✅ Dashboard test completed successfully")
                return True

        except PlaywrightTimeout as e:
            print(f"❌ Timeout error: {e}")
            browser.close()
            return False

        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()
            browser.close()
            return False

if __name__ == "__main__":
    success = test_dashboard()
    sys.exit(0 if success else 1)
