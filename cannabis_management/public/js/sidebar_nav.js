(function () {

    var style = document.createElement('style');
    style.textContent = [
        '.side-menu-icons ul li a { pointer-events: auto !important; }',
        '.item-anchor.block-click { pointer-events: auto !important; }'
    ].join('\n');
    document.head.appendChild(style);

    var clickGuard = typeof WeakSet !== 'undefined' ? new WeakSet() : null;

    function fix() {
        document.querySelectorAll('.side-menu-icons li a').forEach(function (a) {
            var li   = a.parentElement;
            var name = (li && li.getAttribute('data-mmmmm'))
                     || a.getAttribute('title')
                     || a.textContent.replace(/\s+/g, ' ').trim();
            if (!name) return;

            var slug = name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
            if (!slug) return;

            a.setAttribute('href', '/app/' + slug);

            if (clickGuard && !clickGuard.has(a)) {
                clickGuard.add(a);
                a.addEventListener('click', function (e) {
                    if (e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
                        e.preventDefault();
                    }
                }, true);
            }
        });

        document.querySelectorAll('.item-anchor.block-click').forEach(function (el) {
            el.style.setProperty('pointer-events', 'auto', 'important');
        });
    }

    fix();
    var ticks = 0;
    var interval = setInterval(function () {
        fix();
        if (++ticks > 200) clearInterval(interval);
    }, 150);

    $(document).on('page-change show-side-menu', function () {
        ticks = 0;
        setTimeout(fix, 200);
    });

    $(document).on('click', '.side-menu-items a', function () {
        var $li = $(this).closest('li');
        if ($li.parent().hasClass('dropdown-list') && $li.parent().parent().hasClass('side-menu-items')) {
            return;
        }
        $('body').addClass('hide-main-menu');
        $('.btn-toggle-main-menu').removeClass('menu-shown');
    });

}());
