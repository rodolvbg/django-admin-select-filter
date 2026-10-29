import { beforeEach, describe, expect, it, vi } from "vitest";
import {
	addFilter,
	fireDomReady,
	installDjangoJQuery,
	resetJsEnvironment,
} from "./helpers.js";

const modulePath =
	"../../src/django_admin_select_filter/static/admin_select_filter/js/core.js";

function optionElement(option) {
	const element = document.createElement("option");
	if (option !== undefined) element.dataset.option = option;
	return element;
}

describe("the options' data and template", () => {
	beforeEach(() => {
		vi.resetModules();
		resetJsEnvironment();
		delete window.djangoAdminSelectFilterPlugins;
		delete window.djangoAdminSelectFilter;
	});

	it("reads an option's data and html: of an API result, or its <option>", async () => {
		await import(modulePath);
		const { optionOf } = window.djangoAdminSelectFilter;
		expect(
			optionOf({ id: "1", text: "Ana", data: { n: 1 }, html: "<b>Ana</b>" }),
		).toEqual({
			data: { n: 1 },
			html: "<b>Ana</b>",
		});
		expect(optionOf({ id: "1", text: "Ana", data: { n: 1 } })).toEqual({
			data: { n: 1 },
			html: "",
		});
		const element = optionElement(JSON.stringify({ html: "<i>x</i>" }));
		expect(optionOf({ id: "1", element })).toEqual({
			data: {},
			html: "<i>x</i>",
		});
		expect(optionOf({ id: "1", element: optionElement("{broken") })).toEqual({
			data: {},
			html: "",
		});
		expect(optionOf({ id: "1", element: optionElement() })).toEqual({
			data: {},
			html: "",
		});
		expect(optionOf(null)).toEqual({ data: {}, html: "" });
	});

	it("takes the page's plugins: made before it, pushed after, or registered", async () => {
		addFilter();
		const { select2 } = installDjangoJQuery();
		const before = {
			appliesTo: () => true,
			extendOptions: (_element, options) => {
				options.before = true;
			},
		};
		window.djangoAdminSelectFilterPlugins = [before];
		await import(modulePath);
		const pushed = {
			appliesTo: () => true,
			extendOptions: (_element, options) => {
				options.pushed = true;
			},
		};
		window.djangoAdminSelectFilterPlugins.push(pushed);
		window.djangoAdminSelectFilter.register({
			appliesTo: () => true,
			extendOptions: (_element, options) => {
				options.registered = true;
			},
		});
		await fireDomReady();
		expect(select2).toHaveBeenCalledWith(
			expect.objectContaining({ before: true, pushed: true, registered: true }),
		);
		expect(window.djangoAdminSelectFilter.plugins).toBe(
			window.__djangoAdminSelectFilterPlugins,
		);
	});

	it("renders its template's html, in the list and as the selection", async () => {
		addFilter('data-option-template="true"');
		const { select2 } = installDjangoJQuery();
		const span = {
			html: vi.fn(function (html) {
				this.rendered = html;
				return this;
			}),
		};
		const jquery = window.django.jQuery;
		window.django.jQuery = Object.assign(
			vi.fn((target) => (target === "<span>" ? span : jquery(target))),
			{ fn: jquery.fn },
		);
		await import(modulePath);
		await fireDomReady();
		const [{ templateResult, templateSelection }] = select2.mock.calls[0];
		expect(templateSelection).toBe(templateResult);
		const rendered = templateResult({
			id: "1",
			text: "Ana",
			html: "<b>Ana</b>",
		});
		expect(rendered.rendered).toBe("<b>Ana</b>");
		// Without one: its text, as Select2 shows it.
		expect(templateResult({ id: "2", text: "Luis" })).toBe("Luis");
	});

	it("no template, Select2's own rendering", async () => {
		addFilter();
		const { select2 } = installDjangoJQuery();
		await import(modulePath);
		await fireDomReady();
		expect(select2.mock.calls[0][0].templateResult).toBeUndefined();
	});
});

describe("Select2's language", () => {
	beforeEach(() => {
		vi.resetModules();
		resetJsEnvironment();
		delete window.__djangoAdminSelectFilterLanguage;
	});

	it("loads its translations once, and passes its language", async () => {
		addFilter('data-select2-i18n-url="/i18n/es.js" data-language="es"');
		const { select2 } = installDjangoJQuery();
		const append = vi
			.spyOn(document.head, "append")
			.mockImplementation((script) => {
				script.dispatchEvent(new Event("load"));
				return script;
			});
		await import(modulePath);
		await fireDomReady();
		await vi.waitFor(() => expect(select2).toHaveBeenCalledOnce());
		expect(append.mock.calls.map(([script]) => script.src)).toEqual([
			`${window.location.origin}/i18n/es.js`,
		]);
		expect(select2.mock.calls[0][0].language).toBe("es");
		expect(window.__djangoAdminSelectFilterLanguage).toBe("/i18n/es.js");
	});
});
