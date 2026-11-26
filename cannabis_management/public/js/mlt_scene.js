(function () {
	"use strict";

	if (window.MLTScene) return;

	var BASE = "/assets/cannabis_management/images/kiosk/";
	var LOGO = {
		light: BASE + "mlt-light.png",
		dark: BASE + "mlt-dark.png",
		white: BASE + "mlt-white.png",
	};

	var CSS = [
		"@font-face { font-family: 'MLT Display'; src: url('/assets/infix_theme/fonts/bricolage-grotesque-latin.woff2') format('woff2'); font-weight: 200 800; font-display: swap; }",
		"@font-face { font-family: 'MLT Body'; src: url('/assets/infix_theme/fonts/outfit-latin.woff2') format('woff2'); font-weight: 100 900; font-display: swap; }",

		".mlt-scene { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none;",
		"  background: radial-gradient(110% 70% at 50% -10%, #3a1268 0%, rgba(58,18,104,0) 60%), radial-gradient(90% 60% at 50% 115%, #2a0a48 0%, rgba(42,10,72,0) 70%), linear-gradient(180deg, #12061f 0%, #0a0414 55%, #07030d 100%); }",
		".mlt-scene.mlt-contained { position: absolute; }",
		".mlt-scene * { box-sizing: border-box; }",
		".mlt-glow { position: absolute; width: 70vmax; height: 70vmax; border-radius: 50%; will-change: transform; }",
		".mlt-glow-a { left: -22vmax; top: -28vmax; background: radial-gradient(circle, rgba(141,63,214,.34), rgba(141,63,214,0) 65%); animation: mlt-glow-a 26s ease-in-out infinite alternate; }",
		".mlt-glow-b { right: -26vmax; bottom: -32vmax; background: radial-gradient(circle, rgba(203,108,228,.22), rgba(203,108,228,0) 65%); animation: mlt-glow-b 32s ease-in-out infinite alternate; }",
		"@keyframes mlt-glow-a { to { transform: translate3d(18vmax, 10vmax, 0); } }",
		"@keyframes mlt-glow-b { to { transform: translate3d(-16vmax, -12vmax, 0); } }",
		".mlt-horizon { position: absolute; left: 0; right: 0; bottom: 22%; height: 34%; background: radial-gradient(55% 50% at 50% 100%, rgba(203,108,228,.16), rgba(203,108,228,0) 70%); }",
		".mlt-floor { position: absolute; left: -60%; right: -60%; bottom: -2%; height: 56%; transform-origin: 50% 100%; transform: perspective(420px) rotateX(68deg); overflow: hidden;",
		"  -webkit-mask-image: linear-gradient(to top, #000 0%, rgba(0,0,0,.5) 45%, transparent 92%); mask-image: linear-gradient(to top, #000 0%, rgba(0,0,0,.5) 45%, transparent 92%); }",
		".mlt-floor-grid { position: absolute; left: 0; right: 0; top: -96px; bottom: 0; background-image: linear-gradient(rgba(203,108,228,.42) 2px, transparent 2px), linear-gradient(90deg, rgba(203,108,228,.32) 2px, transparent 2px);",
		"  background-size: 96px 96px; background-position: center top; animation: mlt-floor-run 2.8s linear infinite; will-change: transform; }",
		"@keyframes mlt-floor-run { to { transform: translate3d(0, 96px, 0); } }",
		".mlt-field { position: absolute; inset: 0; perspective: 1000px; perspective-origin: 50% 42%; transform-style: preserve-3d; }",
		".mlt-scene img.mlt-fly { position: absolute; left: 50%; top: 42%; width: var(--s); height: auto; max-width: none; margin: calc(var(--s) * -0.44) 0 0 calc(var(--s) * -0.5); opacity: 0; border: 0; will-change: transform, opacity; animation: mlt-fly var(--d) linear var(--delay) infinite; }",
		"@keyframes mlt-fly { 0% { transform: translate3d(var(--x), var(--y), -2400px) rotateZ(var(--r)) rotateY(0deg); opacity: 0; } 10% { opacity: var(--o); } 78% { opacity: var(--o); }",
		"  100% { transform: translate3d(var(--x), var(--y), 650px) rotateZ(calc(var(--r) + var(--spin))) rotateY(var(--ry)); opacity: 0; } }",
		".mlt-vignette { position: absolute; inset: 0; background: radial-gradient(ellipse at 50% 45%, rgba(4,2,8,0) 50%, rgba(4,2,8,.78) 100%); }",

		".mlt-mark { position: relative; perspective: 520px; }",
		".mlt-mark-inner { position: absolute; inset: 0; transform-style: preserve-3d; animation: mlt-mark-swing 7s ease-in-out infinite; }",
		".mlt-mark img.mlt-mark-layer { position: absolute; inset: 0; width: 100%; height: 100%; max-width: none; border: 0; }",
		"@keyframes mlt-mark-swing { 0%, 100% { transform: rotateY(-28deg) rotateX(8deg); } 50% { transform: rotateY(28deg) rotateX(-4deg); } }",
		".mlt-celebrate .mlt-mark { width: 190px; height: 168px; margin: 0 auto 26px; }",
		".mlt-celebrate .mlt-mark-inner { animation: mlt-mark-pop 1s cubic-bezier(.2,.9,.25,1.2) both, mlt-mark-swing 6s ease-in-out 1s infinite; }",
		"@keyframes mlt-mark-pop { from { transform: rotateY(-200deg) rotateX(8deg) scale(.3); } to { transform: rotateY(-28deg) rotateX(8deg) scale(1); } }",

		".mlt-celebrate { position: fixed; inset: 0; z-index: 2147483000; display: flex; align-items: center; justify-content: center; padding: 24px; overflow: hidden; text-align: center;",
		"  font-family: 'MLT Body', 'Outfit', 'Segoe UI', system-ui, sans-serif; color: #f6efff; perspective: 1100px; -webkit-font-smoothing: antialiased; animation: mlt-fade-in .35s ease both; transition: opacity .45s ease; }",
		".mlt-celebrate * { box-sizing: border-box; }",
		".mlt-celebrate.mlt-dismissible { cursor: pointer; }",
		".mlt-celebrate.mlt-leaving { opacity: 0; pointer-events: none; }",
		"@keyframes mlt-fade-in { from { opacity: 0; } }",
		".mlt-tint { position: absolute; inset: 0; background: radial-gradient(circle at 50% 42%, rgba(84,26,140,.78) 0%, rgba(26,8,46,.55) 55%, rgba(7,3,13,.35) 100%); }",
		".mlt-celebrate[data-tone='out'] .mlt-tint { background: radial-gradient(circle at 50% 42%, rgba(126,30,96,.78) 0%, rgba(40,8,42,.55) 55%, rgba(7,3,13,.35) 100%); }",
		".mlt-ring { position: absolute; left: 50%; top: 42%; width: 260px; height: 260px; margin: -130px 0 0 -130px; border-radius: 50%; border: 3px solid rgba(203,108,228,.75); animation: mlt-ring 1.5s ease-out both; }",
		".mlt-ring.mlt-ring-2 { animation-delay: .25s; border-color: rgba(255,255,255,.35); }",
		"@keyframes mlt-ring { from { transform: scale(.3); opacity: 1; } to { transform: scale(3.4); opacity: 0; } }",
		".mlt-burst { position: absolute; left: 50%; top: 42%; width: 0; height: 0; transform-style: preserve-3d; }",
		".mlt-burst img.mlt-burst-logo { position: absolute; width: var(--s); height: auto; max-width: none; border: 0; margin: calc(var(--s) * -0.44) 0 0 calc(var(--s) * -0.5); animation: mlt-burst 1.9s cubic-bezier(.15,.7,.3,1) var(--delay) both; }",
		"@keyframes mlt-burst { 0% { transform: translate3d(0,0,0) scale(.2) rotate(0deg); opacity: 0; } 12% { opacity: 1; } 100% { transform: translate3d(var(--tx), var(--ty), var(--tz)) scale(1) rotate(var(--rot)); opacity: 0; } }",
		".mlt-inner { position: relative; max-width: 980px; }",
		".mlt-kicker { margin: 0; font-size: 20px; font-weight: 600; line-height: 1.3; color: #cdbbe4; animation: mlt-rise .6s .15s both; }",
		".mlt-title { margin: 16px 0 20px; font-family: 'MLT Display', 'Segoe UI', system-ui, sans-serif; font-weight: 800; font-size: clamp(48px, 8.5vw, 112px); line-height: .95; letter-spacing: -.035em; color: #fff; transform-origin: 50% 100%;",
		"  text-shadow: 0 1px 0 #d58cf0, 0 2px 0 #c477e4, 0 3px 0 #b062d4, 0 4px 0 #9a4fc0, 0 5px 0 #833eaa, 0 6px 0 #6c2f93, 0 7px 0 #56227c, 0 8px 0 #421866, 0 22px 44px rgba(0,0,0,.6);",
		"  animation: mlt-title-in .8s cubic-bezier(.2,.9,.25,1.15) .05s both; }",
		".mlt-celebrate[data-tone='out'] .mlt-title { text-shadow: 0 1px 0 #ffb2a0, 0 2px 0 #f59a8c, 0 3px 0 #e47f7c, 0 4px 0 #cc666f, 0 5px 0 #b04f63, 0 6px 0 #923a57, 0 7px 0 #74284a, 0 8px 0 #581b3c, 0 22px 44px rgba(0,0,0,.6); }",
		"@keyframes mlt-title-in { from { opacity: 0; transform: rotateX(80deg) translateY(40px) scale(.9); } }",
		".mlt-msg { margin: 0; font-size: clamp(20px, 2.4vw, 27px); font-weight: 500; line-height: 1.35; color: #f6efff; animation: mlt-rise .6s .3s both; }",
		".mlt-foot { margin: 10px 0 0; font-size: clamp(17px, 2vw, 21px); line-height: 1.35; color: #cdbbe4; animation: mlt-rise .6s .45s both; }",
		".mlt-tap { margin: 36px 0 0; font-size: 15px; color: #8d7aa9; animation: mlt-rise .6s .9s both; }",
		"@keyframes mlt-rise { from { opacity: 0; transform: translateY(16px); } }",

		".mlt-loading { position: fixed; inset: 0; z-index: 2147483000; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none;",
		"  font-family: 'MLT Body', 'Outfit', 'Segoe UI', system-ui, sans-serif; animation: mlt-fade-in .35s ease both; }",
		".mlt-loading img.mlt-loading-mark { position: relative; z-index: 1; width: 190px; height: auto; max-width: none; border: 0;",
		"  filter: drop-shadow(1px 2px 0 #5a1fae) drop-shadow(1px 2px 0 #4a1794) drop-shadow(1px 2px 0 #3d0f78) drop-shadow(1px 2px 0 #2e0a5e) drop-shadow(0 18px 30px rgba(0,0,0,.55));",
		"  animation: mlt-loading-swing 6s ease-in-out infinite; }",
		".mlt-loading-msg { position: relative; z-index: 1; margin: 26px 0 0; font-size: 22px; font-weight: 500; line-height: normal; color: #cdbbe4; animation: mlt-loading-pulse 1.6s ease-in-out infinite; }",
		"@keyframes mlt-loading-swing { 0%, 100% { transform: perspective(520px) rotateY(-24deg) rotateX(6deg); } 50% { transform: perspective(520px) rotateY(24deg) rotateX(-3deg); } }",
		"@keyframes mlt-loading-pulse { 50% { opacity: .55; } }",

		"@media (prefers-reduced-motion: reduce) {",
		"  .mlt-scene img.mlt-fly, .mlt-floor-grid, .mlt-glow, .mlt-mark-inner, .mlt-celebrate .mlt-mark-inner, .mlt-title, .mlt-ring { animation: none !important; }",
		"  .mlt-scene img.mlt-fly { opacity: .3; transform: translate3d(var(--x), var(--y), -700px) rotateZ(var(--r)); }",
		"  .mlt-ring { display: none; }",
		"  .mlt-loading img.mlt-loading-mark, .mlt-loading-msg { animation: none !important; }",
		"}",
	].join("\n");

	var reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
	var current = null;

	function ensureStyles() {
		if (document.getElementById("mlt-scene-style")) return;
		var style = document.createElement("style");
		style.id = "mlt-scene-style";
		style.textContent = CSS;
		(document.head || document.documentElement).appendChild(style);
	}

	function el(tag, className, text) {
		var node = document.createElement(tag);
		if (className) node.className = className;
		if (text != null) node.textContent = text;
		return node;
	}

	function img(src, className) {
		var node = new Image();
		node.src = src;
		node.alt = "";
		node.className = className;
		node.setAttribute("aria-hidden", "true");
		return node;
	}

	function rand(min, max) { return min + Math.random() * (max - min); }

	function buildScene(opts) {
		opts = opts || {};
		var scene = el("div", "mlt-scene" + (opts.contained ? " mlt-contained" : ""));
		scene.setAttribute("aria-hidden", "true");
		scene.appendChild(el("div", "mlt-glow mlt-glow-a"));
		scene.appendChild(el("div", "mlt-glow mlt-glow-b"));
		scene.appendChild(el("div", "mlt-horizon"));
		var floor = el("div", "mlt-floor");
		floor.appendChild(el("div", "mlt-floor-grid"));
		scene.appendChild(floor);

		var field = el("div", "mlt-field");
		var count = opts.count || (window.innerWidth < 700 ? 14 : 26);
		var palette = [
			{ src: LOGO.light, o: 0.55 },
			{ src: LOGO.light, o: 0.45 },
			{ src: LOGO.dark, o: 0.85 },
			{ src: LOGO.dark, o: 0.7 },
			{ src: LOGO.white, o: 0.16 },
		];
		for (var i = 0; i < count; i++) {
			var pick = palette[i % palette.length];
			var logo = img(pick.src, "mlt-fly");
			var duration = rand(30, 54);
			logo.style.setProperty("--x", rand(-62, 62).toFixed(1) + "vw");
			logo.style.setProperty("--y", rand(-46, 46).toFixed(1) + "vh");
			logo.style.setProperty("--s", Math.round(rand(70, 170)) + "px");
			logo.style.setProperty("--o", pick.o);
			logo.style.setProperty("--r", Math.round(rand(-35, 35)) + "deg");
			logo.style.setProperty("--spin", Math.round(rand(-80, 80)) + "deg");
			logo.style.setProperty("--ry", Math.round(rand(-70, 70)) + "deg");
			logo.style.setProperty("--d", duration.toFixed(1) + "s");
			logo.style.setProperty("--delay", (-rand(0, duration)).toFixed(1) + "s");
			field.appendChild(logo);
		}
		scene.appendChild(field);
		scene.appendChild(el("div", "mlt-vignette"));
		return scene;
	}

	function mountBackground(host) {
		ensureStyles();
		host = host || document.body;
		var scene = buildScene();
		host.insertBefore(scene, host.firstChild);
		return scene;
	}

	function buildMark(layers, step) {
		var mark = el("div", "mlt-mark");
		mark.setAttribute("aria-hidden", "true");
		var inner = el("div", "mlt-mark-inner");
		for (var i = layers; i >= 1; i--) {
			var back = img(LOGO.dark, "mlt-mark-layer");
			back.style.transform = "translateZ(" + (-i * step).toFixed(1) + "px)";
			back.style.filter = "brightness(" + (1.3 - (i / layers) * 0.8).toFixed(2) + ")";
			inner.appendChild(back);
		}
		inner.appendChild(img(LOGO.light, "mlt-mark-layer"));
		mark.appendChild(inner);
		return mark;
	}

	function buildBurst() {
		var burst = el("div", "mlt-burst");
		burst.setAttribute("aria-hidden", "true");
		if (reduceMotion) return burst;
		var srcs = [LOGO.light, LOGO.white, LOGO.light, LOGO.dark];
		var count = 20;
		for (var i = 0; i < count; i++) {
			var logo = img(srcs[i % srcs.length], "mlt-burst-logo");
			var angle = (i / count) * Math.PI * 2 + rand(-0.2, 0.2);
			var dist = rand(30, 58);
			logo.style.setProperty("--tx", (Math.cos(angle) * dist).toFixed(1) + "vmax");
			logo.style.setProperty("--ty", (Math.sin(angle) * dist * 0.72).toFixed(1) + "vmax");
			logo.style.setProperty("--tz", Math.round(rand(-150, 450)) + "px");
			logo.style.setProperty("--rot", Math.round(rand(-300, 300)) + "deg");
			logo.style.setProperty("--s", Math.round(rand(44, 120)) + "px");
			logo.style.setProperty("--delay", rand(0, 0.25).toFixed(2) + "s");
			burst.appendChild(logo);
		}
		return burst;
	}

	function dismiss() {
		if (current) current.dismiss();
	}

	function celebrate(opts) {
		opts = opts || {};
		ensureStyles();
		if (current) current.remove();

		var dismissible = opts.dismissible !== false;
		var root = el("div", "mlt-celebrate" + (dismissible ? " mlt-dismissible" : ""));
		root.setAttribute("data-tone", opts.tone || "in");
		root.setAttribute("role", "status");
		root.setAttribute("aria-live", "assertive");

		root.appendChild(buildScene({ contained: true, count: window.innerWidth < 700 ? 10 : 18 }));
		root.appendChild(el("div", "mlt-tint"));
		if (!reduceMotion) {
			root.appendChild(el("div", "mlt-ring"));
			root.appendChild(el("div", "mlt-ring mlt-ring-2"));
		}
		root.appendChild(buildBurst());

		var inner = el("div", "mlt-inner");
		inner.appendChild(buildMark(14, 2.6));
		if (opts.kicker) inner.appendChild(el("p", "mlt-kicker", opts.kicker));
		inner.appendChild(el("div", "mlt-title", opts.title || ""));
		if (opts.message) inner.appendChild(el("p", "mlt-msg", opts.message));
		if (opts.foot) inner.appendChild(el("p", "mlt-foot", opts.foot));
		if (dismissible) inner.appendChild(el("p", "mlt-tap", opts.tap || "Click anywhere to continue"));
		root.appendChild(inner);

		var shownAt = Date.now();
		var timer = null;
		var done = false;

		var handle = {
			element: root,
			remove: function () {
				clearTimeout(timer);
				if (root.parentNode) root.parentNode.removeChild(root);
				if (current === handle) current = null;
			},
			dismiss: function () {
				if (done) return;
				done = true;
				clearTimeout(timer);
				root.classList.add("mlt-leaving");
				setTimeout(handle.remove, 480);
				if (typeof opts.onDone === "function") {
					try { opts.onDone(); } catch (e) {}
				}
			},
		};

		if (dismissible) {
			root.addEventListener("click", function () {
				if (Date.now() - shownAt < 600) return;
				handle.dismiss();
			});
		}
		if (opts.duration) timer = setTimeout(handle.dismiss, opts.duration);

		(document.body || document.documentElement).appendChild(root);
		current = handle;
		return handle;
	}

	function loading(opts) {
		opts = opts || {};
		ensureStyles();
		var root = el("div", "mlt-loading");
		root.setAttribute("role", "status");
		root.setAttribute("aria-live", "polite");
		if (opts.backdrop) root.appendChild(buildScene({ contained: true }));
		root.appendChild(img(LOGO.light, "mlt-loading-mark"));
		root.appendChild(el("p", "mlt-loading-msg", opts.message || "Signing you in\u2026"));
		(document.body || document.documentElement).appendChild(root);
		return root;
	}

	window.MLTScene = {
		LOGO: LOGO,
		ensureStyles: ensureStyles,
		mountBackground: mountBackground,
		celebrate: celebrate,
		loading: loading,
		dismiss: dismiss,
	};
})();
