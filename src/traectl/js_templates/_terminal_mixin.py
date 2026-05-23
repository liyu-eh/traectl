# ── TerminalMixin ──────────────────────────────────────────────

def check_xterm_status():
    return """
    (function() {
        var term = document.querySelector('.xterm');
        if (!term) return 'opened, no xterm element yet';
        var rect = term.getBoundingClientRect();
        return JSON.stringify({visible: rect.width > 0, w: Math.round(rect.width), h: Math.round(rect.height)});
    })()
    """


def read_xterm_content():
    return """
    (function() {
        var xterm = document.querySelector('.xterm');
        if (!xterm) return JSON.stringify({visible: false, content: 'xterm element not found', error: 'no xterm in DOM'});
        var rect = xterm.getBoundingClientRect();
        if (rect.width === 0) return JSON.stringify({visible: false, content: '', error: 'terminal is hidden'});
        var rows = xterm.querySelector('.xterm-rows, .xterm-accessible-rows');
        if (rows) {
            return JSON.stringify({visible: true, rows: rows.children.length, content: rows.textContent.trim().substring(0, 5000)});
        }
        return JSON.stringify({visible: true, content: xterm.textContent.trim().substring(0, 5000)});
    })()
    """


def check_xterm_visible():
    return """(function(){var t=document.querySelector('.xterm'); if(!t) return 'no'; var r=t.getBoundingClientRect(); return r.width>0?'yes':'hidden';})()"""


def type_terminal_command():
    return """
    (function() {
        var input = document.querySelector('.monaco-inputbox input, .quick-open-input input');
        if (!input) return 'no input';
        input.focus();
        input.value = '>Terminal: Create New Integrated Terminal';
        input.dispatchEvent(new Event('input', {bubbles: true}));
        return 'typed';
    })()
    """


def focus_xterm():
    return """
    (function() {
        var xterm = document.querySelector('.xterm');
        if (xterm) { xterm.focus(); return 'focused'; }
        return 'no xterm';
    })()
    """


def read_xterm_output():
    return """
    (function() {
        var xterm = document.querySelector('.xterm');
        if (!xterm) return 'no xterm';
        var rows = xterm.querySelector('.xterm-rows, .xterm-accessible-rows');
        if (rows) return rows.textContent.trim().substring(0, 3000);
        return xterm.textContent.trim().substring(0, 3000);
    })()
    """
