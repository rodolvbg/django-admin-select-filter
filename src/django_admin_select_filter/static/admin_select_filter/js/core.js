function loadScript(source) {
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = source;
		script.addEventListener("load", resolve);
		script.addEventListener("error", reject);
		document.head.append(script);
	});
}

// Capability modules (async_options.js, multiple_navigation.js,
// non_searchable.js, ...) push themselves onto this list. base.html only
// loads the modules a given filter's attributes actually need (e.g.
// async_call, searchable), and since a module script only ever runs once per
// document regardless of how many <script> tags reference it, several filters
// on the same page may request the same module. They don't import this file:
// a bare specifier would need an inline <script type="importmap">, which a
// Content Security Policy without 'unsafe-inline' (or a nonce) blocks.
//
// The page's own plugins, the same way: `window.djangoAdminSelectFilterPlugins`
// (an array, made before this runs, or pushed onto after), or
// `djangoAdminSelectFilter.register(plugin)`. A plugin is `{appliesTo(select),
// extendOptions(select, options), bindEvents($select, select, options)}`:
// `extendOptions` may set any of Select2's options (`templateResult`…).
window.__djangoAdminSelectFilterPlugins ??= [];
const plugins = window.__djangoAdminSelectFilterPlugins;
const own = window.djangoAdminSelectFilterPlugins;
if (Array.isArray(own) && own !== plugins) plugins.push(...own);
window.djangoAdminSelectFilterPlugins = plugins;

/** An option's `data` (the filter's `get_option_data()`) and `html` (its
 * `option_template`): of an API result, or of its `<option>`. */
function optionOf(item) {
	let option = {};
	if (item && ("data" in item || "html" in item)) {
		option = item;
	} else if (item?.element?.dataset?.option) {
		try {
			option = JSON.parse(item.element.dataset.option);
		} catch {
			option = {};
		}
	}
	return { data: option.data ?? {}, html: option.html ?? "" };
}

window.djangoAdminSelectFilter = {
	plugins,
	register(plugin) {
		plugins.push(plugin);
	},
	optionOf,
};

// Select2's translation files register themselves on the global `jQuery`,
// so they load while it points at the jQuery Select2 is attached to.
async function loadSelect2Language(assets) {
	if (!assets.select2I18nUrl || window.__djangoAdminSelectFilterLanguage) {
		return;
	}
	window.__djangoAdminSelectFilterLanguage = assets.select2I18nUrl;
	await loadScript(assets.select2I18nUrl);
}

async function withGlobalJQuery(jquery, callback) {
	const previousJQuery = window.jQuery;
	const previousDollar = window.$;
	window.jQuery = jquery;
	window.$ = jquery;
	try {
		await callback();
	} finally {
		window.jQuery = previousJQuery;
		window.$ = previousDollar;
	}
}

async function ensureSelect2Loaded(assets) {
	if (!window.django?.jQuery) {
		await loadScript(assets.jqueryUrl);
		await loadScript(assets.select2Url);
		await loadSelect2Language(assets);
		await loadScript(assets.jqueryInitUrl);
	} else if (!window.django.jQuery.fn.select2) {
		await withGlobalJQuery(window.django.jQuery, async () => {
			await loadScript(assets.select2Url);
			await loadSelect2Language(assets);
		});
	} else {
		await withGlobalJQuery(window.django.jQuery, () =>
			loadSelect2Language(assets),
		);
	}
}

function bindDefaultNavigation(select) {
	select.on("select2:select", (event) => {
		window.location.assign(event.params.data.id);
	});
}

const FOCUS_TRAP = "[x-trap\\.noautofocus\\.noscroll]";

async function initializeFilters() {
	const filters = document.querySelectorAll(".django-admin-select-filter");
	if (!filters.length) return;

	await ensureSelect2Loaded(filters[0].dataset);
	const $ = window.django.jQuery;

	for (const element of filters) {
		const select = $(element);
		const options = {
			placeholder: element.dataset.placeholder,
			width: "100%",
		};
		if (element.dataset.language) {
			options.language = element.dataset.language;
		}
		if (element.dataset.theme) {
			options.theme = element.dataset.theme;
		}
		// Inside a panel that traps the focus (django-unfold's filters), the
		// dropdown must open inside it too, or its search box can't be typed in.
		const trap = element.closest(FOCUS_TRAP);
		if (trap) {
			options.dropdownParent = $(trap);
		}
		// Its options' template (`option_template`), rendered by the server:
		// in the list, and as the selection.
		if (element.dataset.optionTemplate === "true") {
			const render = (item) => {
				const { html } = optionOf(item);
				return html ? $("<span>").html(html) : item.text;
			};
			options.templateResult = render;
			options.templateSelection = render;
		}
		for (const plugin of plugins) {
			if (plugin.appliesTo(element)) plugin.extendOptions?.(element, options);
		}
		select.select2(options);

		let handled = false;
		for (const plugin of plugins) {
			if (!plugin.appliesTo(element) || !plugin.bindEvents) continue;
			if (plugin.bindEvents(select, element, options) !== false) {
				handled = true;
				break;
			}
		}
		if (!handled) bindDefaultNavigation(select);
	}
}

function run() {
	void initializeFilters();
}

if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", run, { once: true });
} else {
	run();
}
