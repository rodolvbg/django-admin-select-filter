import { beforeEach, describe, expect, it, vi } from "vitest";

const modulePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/admin_select2_filter.js";

function addFilter() {
	document.body.innerHTML = `
    <select
      class="admin-select2-filter"
      data-placeholder="Search"
      data-jquery-url="/jquery.js"
      data-jquery-init-url="/jquery.init.js"
      data-select2-url="/select2.js"
    ></select>
  `;
}

function addAsyncFilter() {
	document.body.innerHTML = `
    <select
      class="admin-select2-filter"
      data-placeholder="Search"
      data-jquery-url="/jquery.js"
      data-jquery-init-url="/jquery.init.js"
      data-select2-url="/select2.js"
      data-async-call="true"
      data-api-url="/admin/select-filter/options/"
      data-app-label="testapp"
      data-model-name="book"
      data-parameter-name="author"
      data-all-value="__all__"
    ></select>
  `;
}

function installDjangoJQuery({ select2Installed = true } = {}) {
	const select2 = vi.fn();
	const on = vi.fn();
	const jquery = vi.fn(() => ({ select2, on }));
	jquery.fn = select2Installed ? { select2: vi.fn() } : {};
	window.django = { jQuery: jquery };
	return { jquery, on, select2 };
}

describe("admin Select2 filter", () => {
	beforeEach(() => {
		vi.resetModules();
		document.head.innerHTML = "";
		document.body.innerHTML = "";
		delete window.django;
		delete window.jQuery;
		delete window.$;
		window.history.replaceState({}, "", "/");
	});

	it("does nothing when the page has no filters", async () => {
		await import(modulePath);

		expect(document.head.querySelector("script")).toBeNull();
	});

	it("initializes Select2 with the Django jQuery instance", async () => {
		addFilter();
		const { jquery, on, select2 } = installDjangoJQuery();
		await import(modulePath);

		expect(jquery).toHaveBeenCalledOnce();
		expect(select2).toHaveBeenCalledWith({
			placeholder: "Search",
			width: "100%",
		});
		expect(on).toHaveBeenCalledWith("select2:select", expect.any(Function));
	});

	it("loads Select2 temporarily against Django's isolated jQuery", async () => {
		addFilter();
		const { jquery, select2 } = installDjangoJQuery({
			select2Installed: false,
		});
		const originalDollar = window.$;
		const append = vi
			.spyOn(document.head, "append")
			.mockImplementation((script) => {
				expect(window.jQuery).toBe(jquery);
				jquery.fn.select2 = vi.fn();
				script.dispatchEvent(new Event("load"));
				return script;
			});
		await import(modulePath);
		await vi.waitFor(() => expect(select2).toHaveBeenCalledOnce());

		expect(append).toHaveBeenCalledOnce();
		expect(window.$).toBe(originalDollar);
	});

	it("loads jQuery, Select2 and jquery.init when Django jQuery is absent", async () => {
		addFilter();
		const select2 = vi.fn();
		const on = vi.fn();
		const jquery = vi.fn(() => ({ select2, on }));
		jquery.fn = {};
		const sources = [];
		vi.spyOn(document.head, "append").mockImplementation((script) => {
			sources.push(new URL(script.src).pathname);
			if (script.src.endsWith("/jquery.js")) window.jQuery = jquery;
			if (script.src.endsWith("/select2.js")) jquery.fn.select2 = vi.fn();
			if (script.src.endsWith("/jquery.init.js")) {
				window.django = { jQuery: jquery };
				delete window.jQuery;
			}
			script.dispatchEvent(new Event("load"));
			return script;
		});

		await import(modulePath);
		await vi.waitFor(() => expect(select2).toHaveBeenCalledOnce());

		expect(sources).toEqual(["/jquery.js", "/select2.js", "/jquery.init.js"]);
	});

	it("navigates to the selected choice", async () => {
		addFilter();
		const { on } = installDjangoJQuery();
		await import(modulePath);
		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];

		selectHandler({ params: { data: { id: "#selected" } } });

		expect(window.location.hash).toBe("#selected");
	});

	it("loads asynchronous options from the filter API", async () => {
		addAsyncFilter();
		const { on, select2 } = installDjangoJQuery();
		const consoleError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		window.history.replaceState({}, "", "/admin/testapp/book/?p=2");
		await import(modulePath);

		const options = select2.mock.calls[0][0];
		expect(options.ajax.url).toBe("/admin/select-filter/options/");
		expect(options.ajax.data({ term: "row" })).toEqual({
			app_label: "testapp",
			model_name: "book",
			parameter_name: "author",
			facets: false,
			q: "row",
		});
		expect(options.ajax.data({}).q).toBe("");

		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];
		selectHandler({ params: { data: { id: "7" } } });

		expect(consoleError).toHaveBeenCalled();
	});

	it("requests facet counts when the changelist enables them", async () => {
		addAsyncFilter();
		document.querySelector("select").dataset.facets = "true";
		const { select2 } = installDjangoJQuery();
		await import(modulePath);

		expect(select2.mock.calls[0][0].ajax.data({}).facets).toBe(true);
	});

	it("removes an asynchronous filter when All is selected", async () => {
		addAsyncFilter();
		const { on } = installDjangoJQuery();
		const consoleError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		window.history.replaceState({}, "", "/admin/testapp/book/?author=7&p=2");
		await import(modulePath);
		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];

		selectHandler({ params: { data: { id: "__all__" } } });

		expect(consoleError).toHaveBeenCalled();
	});
});
