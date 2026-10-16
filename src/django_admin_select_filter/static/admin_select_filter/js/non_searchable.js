// Loaded only when a filter has searchable = False (see base.html).
// Registered with core.js, which reads this list once the page is parsed.
window.__djangoAdminSelectFilterPlugins ??= [];
window.__djangoAdminSelectFilterPlugins.push({
	appliesTo: (element) => element.dataset.searchable === "false",

	extendOptions: (_element, options) => {
		options.minimumResultsForSearch = Number.POSITIVE_INFINITY;
	},
});
