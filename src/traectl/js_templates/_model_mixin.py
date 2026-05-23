# ── ModelMixin ─────────────────────────────────────────────────

def query_current_model(selector):
    return f"""
    (function() {{
        var cur = document.querySelector('{selector}');
        return cur ? cur.textContent.trim() : '';
    }})()
    """


def count_model_items(selector):
    return f"""
    (function() {{
        var items = document.querySelectorAll('{selector}');
        return items.length;
    }})()
    """


def query_model_list(selectors):
    return f"""
    (function() {{
        var items = document.querySelectorAll('{selectors["model_item"]}');
        var models = [];
        for (var i = 0; i < items.length; i++) {{
            var nameEl = items[i].querySelector('{selectors["model_item_name"]}');
            var name = nameEl ? nameEl.textContent.trim() : '';
            if (name) {{ models.push(name); }}
        }}
        var cur = document.querySelector('{selectors["model_trigger_value"]}');
        return JSON.stringify({{
            currentModel: cur ? cur.textContent.trim() : '',
            availableModels: models
        }}, null, 2);
    }})()
    """


def click_model_item(selectors, json_name):
    return f"""
    (function() {{
        var items = document.querySelectorAll('{selectors["model_item"]}');
        for (var i = 0; i < items.length; i++) {{
            var nameEl = items[i].querySelector('{selectors["model_item_name"]}');
            var name = nameEl ? nameEl.textContent.trim() : '';
            if (name === {json_name}) {{
                items[i].scrollIntoView({{block: 'center'}});
                items[i].click();
                return 'switched to ' + name;
            }}
        }}
        var available = [];
        for (var i = 0; i < items.length; i++) {{
            var n = items[i].querySelector('{selectors["model_item_name"]}');
            if (n) available.push(n.textContent.trim());
        }}
        return JSON.stringify({{error: '模型未找到', available: available}});
    }})()
    """


def trigger_model_selector(selector):
    return f"""
    (function() {{
        var t = document.querySelector('{selector}');
        if (t) {{
            t.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
        }}
    }})()
    """


def trigger_model_selector_js():
    return """
    (function() {
        var t = document.querySelector('.icube-model-select-trigger');
        if (t) {
            t.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
        }
    })()
    """
