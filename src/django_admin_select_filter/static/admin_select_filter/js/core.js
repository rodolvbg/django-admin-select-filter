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

async function ensureSelect2Loaded(assets) {
	if (!window.django?.jQuery) {
		await loadScript(assets.jqueryUrl);
		await loadScript(assets.select2Url);
		await loadScript(assets.jqueryInitUrl);
	} else if (!window.django.jQuery.fn.select2) {
		const previousJQuery = window.jQuery;
		const previousDollar = window.$;
		window.jQuery = window.django.jQuery;
		window.$ = window.django.jQuery;
		try {
			await loadScript(assets.select2Url);
		} finally {
			window.jQuery = previousJQuery;
			window.$ = previousDollar;
		}
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
