# ── EditorMixin ────────────────────────────────────────────────

def query_editor_state():
    return """
    (function() {
        var result = {openTabs: [], activeTab: '', activeFilePath: '', editorContent: '', editorEmpty: true};
        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            var t = tabs[i];
            result.openTabs.push({
                index: i,
                title: t.textContent.trim(),
                active: t.classList.contains('active'),
                resource: t.getAttribute('data-resource') || t.getAttribute('title') || ''
            });
            if (t.classList.contains('active')) {
                result.activeTab = t.textContent.trim();
            }
        }
        var activeTab = document.querySelector('.tab.active');
        if (activeTab) {
            var uri = activeTab.getAttribute('data-resource');
            if (!uri) {
                var label = activeTab.querySelector('.monaco-icon-label-description');
                if (label) uri = label.textContent.trim();
            }
            if (!uri) uri = activeTab.getAttribute('title') || '';
            result.activeFilePath = uri;
        }
        var viewLines = document.querySelector('.monaco-editor .view-lines');
        if (viewLines) {
            var lines = viewLines.querySelectorAll('.view-line');
            var texts = [];
            for (var i = 0; i < lines.length; i++) {
                texts.push(lines[i].textContent);
            }
            result.editorContent = texts.join('\\n');
            result.editorEmpty = result.editorContent.trim().length === 0;
        } else {
            var editorArea = document.querySelector('[id="workbench.parts.editor"] .content');
            if (editorArea) {
                var text = editorArea.textContent.trim().substring(0, 3000);
                if (text && text !== 'Uh..no content yet') {
                    result.editorContent = text;
                    result.editorEmpty = false;
                }
            }
        }
        return JSON.stringify(result, null, 2);
    })()
    """


def query_file_changes():
    return """
    (function() {
        var result = {changes: [], diffViews: []};
        var diffView = document.querySelector('[id="main"].solo_diff_view');
        if (diffView && diffView.style.display !== 'none') {
            var diffText = diffView.textContent.trim().substring(0, 2000);
            result.diffViews.push({type: 'solo_diff_view', content: diffText});
        }
        var sidebar = document.querySelector('[id="workbench.parts.solo.aiSidebar"]');
        if (sidebar) {
            var cards = sidebar.querySelectorAll('[class*=card], [class*=item], [class*=change]');
            for (var i = 0; i < cards.length; i++) {
                var c = cards[i];
                var text = c.textContent.trim();
                if (!text) continue;
                var rect = c.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && text.length > 3) {
                    var fileMatch = text.match(/[\\w\\-]+\\.\\w+/);
                    result.changes.push({
                        text: text.substring(0, 200),
                        hasFile: fileMatch ? fileMatch[0] : null,
                        visible: true
                    });
                }
            }
            var btns = sidebar.querySelectorAll('button');
            var actions = [];
            for (var i = 0; i < btns.length; i++) {
                var txt = btns[i].textContent.trim();
                if (txt && (txt.indexOf('Accept') !== -1 || txt.indexOf('Reject') !== -1 ||
                    txt.indexOf('接受') !== -1 || txt.indexOf('拒绝') !== -1 ||
                    txt.indexOf('Apply') !== -1 || txt.indexOf('应用') !== -1 ||
                    txt.indexOf('全部') !== -1 || txt === '✓' || txt === '✗')) {
                    actions.push({text: txt, visible: btns[i].offsetParent !== null});
                }
            }
            if (actions.length > 0) result.actions = actions;
        }
        var diffEditors = document.querySelectorAll('.monaco-diff-editor');
        for (var i = 0; i < diffEditors.length; i++) {
            var de = diffEditors[i];
            var rect = de.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                result.diffViews.push({type: 'monaco-diff-editor', visible: true});
            }
        }
        return JSON.stringify(result, null, 2);
    })()
    """


def click_accept_btn():
    return """
    (function() {
        var diffView = document.querySelector('[id="main"].solo_diff_view');
        if (diffView) {
            var btns = diffView.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var txt = btns[i].textContent.trim();
                if (txt === 'Accept' || txt.indexOf('接受') !== -1 || txt === '\u2713') {
                    btns[i].click();
                    return '已点击 Accept';
                }
            }
        }
        var sidebar = document.querySelector('[id="workbench.parts.solo.aiSidebar"]');
        if (sidebar) {
            var btns = sidebar.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var txt = btns[i].textContent.trim();
                if (txt === 'Accept All' || txt.indexOf('全部接受') !== -1 ||
                    txt === 'Accept' || txt.indexOf('接受') !== -1) {
                    if (btns[i].offsetParent !== null) {
                        btns[i].click();
                        return '已点击: ' + txt;
                    }
                }
            }
        }
        return '未找到接受按钮（当前可能没有待接受的变更）';
    })()
    """


def click_reject_btn():
    return """
    (function() {
        var diffView = document.querySelector('[id="main"].solo_diff_view');
        if (diffView) {
            var btns = diffView.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var txt = btns[i].textContent.trim();
                if (txt === 'Reject' || txt.indexOf('拒绝') !== -1 || txt === '\u2717') {
                    btns[i].click();
                    return '已点击 Reject';
                }
            }
        }
        var sidebar = document.querySelector('[id="workbench.parts.solo.aiSidebar"]');
        if (sidebar) {
            var btns = sidebar.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var txt = btns[i].textContent.trim();
                if (txt === 'Reject All' || txt.indexOf('全部拒绝') !== -1 ||
                    txt === 'Reject' || txt.indexOf('拒绝') !== -1) {
                    if (btns[i].offsetParent !== null) {
                        btns[i].click();
                        return '已点击: ' + txt;
                    }
                }
            }
        }
        return '未找到拒绝按钮';
    })()
    """


def salvage_editor_text():
    return """
    (function() {
        var editor = document.querySelector('.monaco-editor .view-lines');
        if (!editor) return '';
        var lines = editor.querySelectorAll('.view-line');
        var text = '';
        for (var i = 0; i < lines.length; i++) {
            text += lines[i].textContent + '\n';
        }
        return text.trim().substring(0, 3000);
    })()
    """
