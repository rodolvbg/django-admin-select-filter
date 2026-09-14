import { registerPlugin } from "core";

// Loaded only when a filter has searchable = False (see base.html).
registerPlugin({
	appliesTo: (element) => element.dataset.searchable === "false",

	extendOptions: (_element, options) => {
		options.minimumResultsForSearch = Number.POSITIVE_INFINITY;
	},
});
