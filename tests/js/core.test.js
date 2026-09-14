import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	addFilter,
	fireDomReady,
	installDjangoJQuery,
	resetJsEnvironment,
} from "./helpers.js";

const modulePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/core.js";

describe("core", () => {
	beforeEach(() => {
		vi.resetModules();
		resetJsEnvironment();
	});

	it("does nothing when the page has no filters", async () => {
		await import(modulePath);
		await fireDomReady();

		expect(document.head.querySelector("script")).toBeNull();
	});

	it("defers initialization until DOMContentLoaded", async () => {
		addFilter();
		const { select2 } = installDjangoJQuery();
		await import(modulePath);

		expect(select2).not.toHaveBeenCalled();

		await fireDomReady();

		expect(select2).toHaveBeenCalledOnce();
	});

	it("initializes immediately when the document is already loaded", async () => {
		addFilter();
		const { select2 } = installDjangoJQuery();
		Object.defineProperty(document, "readyState", {
			configurable: true,
			get: () => "complete",
		});

		await import(modulePath);

		expect(select2).toHaveBeenCalledOnce();
	});

	it("initializes Select2 with the Django jQuery instance", async () => {
		addFilter();
		const { jquery, on, select2 } = installDjangoJQuery();
		await import(modulePath);
		await fireDomReady();

		expect(jquery).toHaveBeenCalledOnce();
		expect(select2).toHaveBeenCalledWith({
			placeholder: "Search",
			width: "100%",
		});
		expect(on).toHaveBeenCalledWith("select2:select", expect.any(Function));
	});

	it("navigates to the selected choice by default", async () => {
		addFilter();
		const { on } = installDjangoJQuery();
		await import(modulePath);
		await fireDomReady();
		const selectHandler = on.mock.calls.find(
			([eventName]) => eventName === "select2:select",
		)[1];

		selectHandler({ params: { data: { id: "#selected" } } });

		expect(window.location.hash).toBe("#selected");
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
		await fireDomReady();
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
		await fireDomReady();
		await vi.waitFor(() => expect(select2).toHaveBeenCalledOnce());

		expect(sources).toEqual(["/jquery.js", "/select2.js", "/jquery.init.js"]);
	});

	it("applies extendOptions only for plugins whose appliesTo matches", async () => {
		addFilter();
		const { select2 } = installDjangoJQuery();
		const matching = {
			appliesTo: () => true,
			extendOptions: (_element, options) => {
				options.matched = true;
			},
		};
		const notMatching = {
			appliesTo: () => false,
			extendOptions: vi.fn(),
		};
		window.__djangoAdminSelectFilterPlugins = [matching, notMatching];

		await import(modulePath);
		await fireDomReady();

		expect(select2).toHaveBeenCalledWith({
			placeholder: "Search",
			width: "100%",
			matched: true,
		});
		expect(notMatching.extendOptions).not.toHaveBeenCalled();
	});

	it("falls back to default navigation when a plugin declines to bind events", async () => {
		addFilter();
		const { on } = installDjangoJQuery();
		const declining = {
			appliesTo: () => true,
			bindEvents: vi.fn(() => false),
		};
		window.__djangoAdminSelectFilterPlugins = [declining];

		await import(modulePath);
		await fireDomReady();

		expect(declining.bindEvents).toHaveBeenCalledOnce();
		expect(on).toHaveBeenCalledWith("select2:select", expect.any(Function));
	});

	it("skips default navigation and later plugins once a plugin handles events", async () => {
		addFilter();
		const { on } = installDjangoJQuery();
		const handling = {
			appliesTo: () => true,
			bindEvents: (select) => {
				select.on("custom:event", () => {});
				return true;
			},
		};
		const neverReached = { appliesTo: () => true, bindEvents: vi.fn() };
		window.__djangoAdminSelectFilterPlugins = [handling, neverReached];

		await import(modulePath);
		await fireDomReady();

		expect(neverReached.bindEvents).not.toHaveBeenCalled();
		expect(on).toHaveBeenCalledWith("custom:event", expect.any(Function));
		expect(on).not.toHaveBeenCalledWith("select2:select", expect.any(Function));
	});
});
