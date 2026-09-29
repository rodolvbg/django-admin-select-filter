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
// non_searchable.js, ...) register themselves here. base.html only loads the
// modules a given filter's attributes actually need (e.g. async_call,
// searchable), and since a module script only ever runs once per document
// regardless of how many <script> tags reference it, registering here is
// safe even though several filters on the same page may request the same
// module.
window.__djangoAdminSelectFilterPlugins ??= [];
const plugins = window.__djangoAdminSelectFilterPlugins;

export function registerPlugin(plugin) {
	plugins.push(plugin);
}

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
