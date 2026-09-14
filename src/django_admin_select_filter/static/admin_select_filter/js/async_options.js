import { registerPlugin } from "./core.js";

// Loaded only when a filter has async_call = True (see base.html).
registerPlugin({
	appliesTo: (element) => element.dataset.asyncCall === "true",

	extendOptions: (element, options) => {
		options.ajax = {
			url: element.dataset.apiUrl,
			data: (params) => ({
				app_label: element.dataset.appLabel,
				model_name: element.dataset.modelName,
				parameter_name: element.dataset.parameterName,
				facets: element.dataset.facets === "true",
				q: params.term ?? "",
			}),
		};
	},

	// A multiple-select filter always navigates through its own close
	// handler (see multiple_navigation.js) regardless of async_call, so this
	// only binds the single-select case.
	bindEvents: (select, element) => {
		if (element.dataset.multiple === "true") return false;

		select.on("select2:select", (event) => {
			if (event.params.data.element) {
				window.location.assign(event.params.data.id);
				return;
			}
			const url = new URL(window.location.href);
			if (event.params.data.id === element.dataset.allValue) {
				url.searchParams.delete(element.dataset.parameterName);
			} else {
				url.searchParams.set(
					element.dataset.parameterName,
					event.params.data.id,
				);
			}
			url.searchParams.delete("p");
			window.location.assign(url.toString());
		});
		return true;
	},
});
