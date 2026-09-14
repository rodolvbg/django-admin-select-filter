import { registerPlugin } from "./core.js";

// Loaded only when a filter has multiple = True (see base.html).
registerPlugin({
	appliesTo: (element) => element.dataset.multiple === "true",

	bindEvents: (select, element) => {
		select.on("select2:close", () => {
			const values = [].concat(select.val() || []).filter(Boolean);
			const url = new URL(window.location.href);
			if (values.length === 0) {
				url.searchParams.delete(element.dataset.parameterName);
			} else {
				url.searchParams.set(
					element.dataset.parameterName,
					values.join(element.dataset.multipleSeparator),
				);
			}
			url.searchParams.delete("p");
			window.location.assign(url.toString());
		});
		return true;
	},
});
