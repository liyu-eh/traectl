# ── MediaMixin ─────────────────────────────────────────────────

def click_retry_btn():
    return """
    (() => {
        let btn = document.querySelector('button[aria-label="重试"]');
        if (btn && !btn.disabled) { btn.click(); return 'retry-clicked'; }
        const allBtns = document.querySelectorAll('button');
        for (const b of allBtns) {
            if ((b.textContent || '').trim() === '' &&
                b.getAttribute('aria-label') === '重试' &&
                !b.disabled && b.offsetWidth > 0) {
                b.click();
                return 'retry-clicked-v2';
            }
        }
        return 'no-retry-button';
    })()
    """


def close_dialog_overlay(selector):
    return f"""
    (() => {{
        const cancelBtns = document.querySelectorAll('button, [role="button"]');
        for (const b of cancelBtns) {{
            const text = (b.textContent || '').trim();
            if (['取消', '关闭', 'Cancel', 'Close', '✕', '×', 'x'].includes(text) &&
                !b.disabled && b.offsetWidth > 0) {{
                b.click();
                return 'closed-via-cancel:' + text;
            }}
        }}
        const overlays = document.querySelectorAll('{selector}');
        for (const o of overlays) {{
            if (o.offsetWidth > 0) {{
                const closeBtn = o.querySelector('[class*="close"], [class*="Close"], [aria-label*="close"], [aria-label*="Close"]');
                if (closeBtn && !closeBtn.disabled) {{
                    closeBtn.click();
                    return 'closed-via-overlay-close';
                }}
            }}
        }}
        return 'js-no-close-found';
    }})()
    """


def dispatch_escape_keydown():
    return """
    (function() {
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true}));
    })()
    """


def dispatch_escape_keyup():
    return """
    (function() {
        document.dispatchEvent(new KeyboardEvent('keyup', {key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true}));
    })()
    """


def scan_dialogs():
    return """
    (() => {
        const overlays = document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="mask"], [class*="backdrop"], [class*="dialog"], [role="dialog"]');
        const dialogs = [];
        for (const o of overlays) {
            if (o.offsetWidth > 0 || o.offsetHeight > 0) {
                const text = (o.textContent || '').trim();
                if (text) {
                    const buttons = o.querySelectorAll('button, [role="button"]');
                    const btnTexts = [];
                    for (const b of buttons) {
                        const t = (b.textContent || '').trim();
                        if (t && !b.disabled && b.offsetWidth > 0) {
                            btnTexts.push(t);
                        }
                    }
                    dialogs.push({text: text.substring(0, 500), buttons: btnTexts});
                }
            }
        }
        return JSON.stringify(dialogs);
    })()
    """


def check_dialog_dismissed():
    return """
    (() => {
        const overlays = document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="mask"], [class*="backdrop"], [class*="dialog"], [role="dialog"]');
        for (const o of overlays) {
            if (o.offsetWidth > 0) return 'still-visible';
        }
        return 'dismissed';
    })()
    """


def click_overlay_button(target):
    return f"""
    (() => {{
        const overlays = document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="mask"], [class*="backdrop"], [class*="dialog"], [role="dialog"]');
        for (const o of overlays) {{
            if (o.offsetWidth > 0) {{
                const buttons = o.querySelectorAll('button, [role="button"]');
                for (const b of buttons) {{
                    const t = (b.textContent || '').trim();
                    if (t.includes({target!r}) && !b.disabled && b.offsetWidth > 0) {{
                        b.click();
                        return true;
                    }}
                }}
            }}
        }}
        return false;
    }})()
    """
