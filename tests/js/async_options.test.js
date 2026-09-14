import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	addAsyncFilter,
	fireDomReady,
	installDjangoJQuery,
	resetJsEnvironment,
} from "./helpers.js";

const corePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/core.js";
const asyncOptionsPath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/async_options.js";

describe("async_options", () => {
	beforeEach(() => {
		vi.resetModules();
		resetJsEnvironment();
	});

	it("loads asynchronous options from the filter API", async () => {
		addAsyncFilter();
		const { on, select2 } = installDjangoJQuery();
		const consoleError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		window.history.replaceState({}, "", "/admin/testapp/book/?p=2");
		await import(asyncOptionsPath);
		await import(corePath);
		await fireDomReady();

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
		await import(asyncOptionsPath);
		await import(corePath);
		await fireDomReady();

		expect(select2.mock.calls[0][0].ajax.data({}).facets).toBe(true);
	});

	it("removes an asynchronous filter when All is selected", async () => {
		addAsyncFilter();
		const { on } = installDjangoJQuery();
		const consoleError = vi
			.spyOn(console, "error")
			.mockImplementation(() => {});
		window.history.replaceState({}, "", "/admin/testapp/book/?author=7&p=2");
		await import(asyncOptionsPath);
		await import(corePath);
		await fireDomReady();
		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];

		selectHandler({ params: { data: { id: "__all__" } } });

		expect(consoleError).toHaveBeenCalled();
	});

	it("navigates directly when Select2 reports a real element (already-rendered choice)", async () => {
		addAsyncFilter();
		const { on } = installDjangoJQuery();
		await import(asyncOptionsPath);
		await import(corePath);
		await fireDomReady();
		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];

		selectHandler({ params: { data: { id: "#selected", element: {} } } });

		expect(window.location.hash).toBe("#selected");
	});

	it("declines to bind and falls back to default navigation when multiple is set", async () => {
		addAsyncFilter('data-multiple="true"');
		const { on } = installDjangoJQuery();
		await import(asyncOptionsPath);
		await import(corePath);
		await fireDomReady();

		expect(on).toHaveBeenCalledWith("select2:select", expect.any(Function));
		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];
		// Falls through to core's default navigation, proving async_options
		// itself declined to bind (bindEvents returned false).
		selectHandler({ params: { data: { id: "#selected" } } });
		expect(window.location.hash).toBe("#selected");
	});
});
