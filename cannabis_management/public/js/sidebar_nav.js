// Sidebar link fix — adds href to workspace icons so Chrome shows "Open link in new tab"
// Runs every 150ms to re-add href after any Vue re-render removes it.

(function () {

    // Inject CSS once
    var style = document.createElement('style');
    style.textContent = [
        // Ensure clicks reach the <a> element
        '.side-menu-icons ul li a { pointer-events: auto !important; }',
        '.item-anchor.block-click { pointer-events: auto !important; }'
    ].join('\n');
    document.head.appendChild(style);

    var clickGuard = typeof WeakSet !== 'undefined' ? new WeakSet() : null;

    function fix() {
        // ── Vue sidebar icons (left purple column) ──────────────────
        document.querySelectorAll('.side-menu-icons li a').forEach(function (a) {
            // Get workspace name from parent li[data-mmmmm], then title attr, then text
            var li   = a.parentElement;
            var name = (li && li.getAttribute('data-mmmmm'))
                     || a.getAttribute('title')
                     || a.textContent.replace(/\s+/g, ' ').trim();
            if (!name) return;

            var slug = name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
            if (!slug) return;

            // Always set href (Vue only tracks onClick/title/data-toggle, not href)
            a.setAttribute('href', '/app/' + slug);

            // One-time: prevent left-click following the href (Vue onClick handles routing)
            if (clickGuard && !clickGuard.has(a)) {
                clickGuard.add(a);
                a.addEventListener('click', function (e) {
                    if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
                        e.preventDefault();
                    }
                }, true);
            }
        });

        // ── Frappe workspace sidebar (right panel, already has href) ─
        document.querySelectorAll('.item-anchor.block-click').forEach(function (el) {
            el.style.setProperty('pointer-events', 'auto', 'important');
        });
    }

    // Run immediately and every 150 ms for 30 s (handles Vue re-renders)
    fix();
    var ticks = 0;
    var interval = setInterval(function () {
        fix();
        if (++ticks > 200) clearInterval(interval);
    }, 150);

    // Also re-run on Frappe navigation
    $(document).on('page-change show-side-menu', function () {
        ticks = 0; // reset the 30-second window
        setTimeout(fix, 200);
    });

}());
