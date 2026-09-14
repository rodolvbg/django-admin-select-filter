function loadScript(source) {
	return new Promise((resolve, reject) => {
		const script = document.createElement("script");
		script.src = source;
		script.addEventListener("load", resolve);
		script.addEventListener("error", reject);
		document.head.append(script);
	});
}

async function initializeFilters() {
	const filters = document.querySelectorAll(".django-admin-select-filter");
	if (!filters.length) return;

	const assets = filters[0].dataset;
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

	const $ = window.django.jQuery;

	for (const element of filters) {
		const select = $(element);
		const options = {
			placeholder: element.dataset.placeholder,
			width: "100%",
		};
		if (element.dataset.asyncCall === "true") {
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
		}
		select.select2(options);
		if (element.dataset.autocomplete === "true") {
			select.on("select2:open", () => {
				document
					.querySelector(".select2-container--open .select2-search__field")
					?.setAttribute("autocomplete", "off");
			});
		}
		if (element.dataset.multiple === "true") {
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
		} else {
			select.on("select2:select", (event) => {
				if (
					element.dataset.asyncCall === "true" &&
					!event.params.data.element
				) {
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
				} else {
					window.location.assign(event.params.data.id);
				}
			});
		}
	}
}

void initializeFilters();
