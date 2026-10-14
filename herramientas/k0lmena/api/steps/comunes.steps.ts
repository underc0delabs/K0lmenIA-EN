// api/steps/comunes.steps.ts
//
// Steps genéricos de API en español. El agente api-mapper arma los .feature
// usando SOLO estos steps, así no hace falta escribir código por cada endpoint.
//
// Variables en endpoints, headers y bodies: {nombre}
//   - se reemplaza por un valor guardado con "guardo el campo ... como ..."
//   - o, si no existe, por la variable de entorno del mismo nombre (.env)
//
// GraphQL: "envío la consulta GraphQL:" manda {query, variables} por POST al endpoint GraphQL
// (el de "el endpoint GraphQL es ...", o GRAPHQL_URL del .env, o API_BASEURL + /graphql). La query
// va tal cual (sus llaves no se interpolan): los valores dinámicos van en las variables GraphQL,
// que sí aceptan {nombre}.
import '../../env'; // .env único de la raíz de k0lmenIA
import { Given, When, Then, Before, After, DataTable } from '@cucumber/cucumber';
import { expect } from '@playwright/test';
import axios, { AxiosResponse, Method } from 'axios';
import { variables, interpolar } from '../../tools/variables';

type Estado = {
  headers: Record<string, string>;
  graphql: { endpoint?: string; variables?: Record<string, unknown> };
  request?: { metodo: string; url: string; body?: unknown };
  response?: AxiosResponse;
  ms?: number;
};

let estado: Estado;

Before(() => {
  estado = { headers: { 'Content-Type': 'application/json' }, graphql: {} };
});


// Lee un campo con notación de puntos: "data.items.0.id"
const leerCampo = (obj: unknown, ruta: string): unknown =>
  ruta.split('.').reduce<any>((acc, k) => (acc == null ? undefined : acc[k]), obj);

const respuesta = (): AxiosResponse => {
  if (!estado.response) throw new Error('Todavía no se envió ningún request en este escenario.');
  return estado.response;
};

const enviar = async (metodo: string, endpoint: string, body?: string) => {
  const baseURL = process.env.API_BASEURL ?? '';
  const url = /^https?:\/\//.test(endpoint) ? interpolar(endpoint) : `${baseURL}${interpolar(endpoint)}`;
  const inicio = Date.now();
  estado.request = { metodo: metodo.toUpperCase(), url, body: body !== undefined ? JSON.parse(interpolar(body)) : undefined };
  estado.response = await axios.request({
    method: metodo.toUpperCase() as Method,
    url,
    headers: estado.headers,
    data: body !== undefined ? JSON.parse(interpolar(body)) : undefined,
    validateStatus: () => true, // los 4xx/5xx se validan en los Then, no tiran excepción
  });
  estado.ms = Date.now() - inicio;
};

// GraphQL: POST con {query, variables, operationName} al endpoint GraphQL.
const urlGraphQL = (): string => {
  const destino = interpolar(estado.graphql.endpoint ?? process.env.GRAPHQL_URL ?? '/graphql');
  return /^https?:\/\//.test(destino) ? destino : `${process.env.API_BASEURL ?? ''}${destino}`;
};

const enviarGraphQL = async (query: string) => {
  const url = urlGraphQL();
  const operacion = /^\s*(?:query|mutation|subscription)\s+([A-Za-z_]\w*)/.exec(query)?.[1];
  const body = { query, variables: estado.graphql.variables ?? {}, ...(operacion ? { operationName: operacion } : {}) };
  const inicio = Date.now();
  estado.request = { metodo: 'POST', url, body };
  estado.response = await axios.request({
    method: 'POST', url, headers: estado.headers, data: body,
    validateStatus: () => true,
  });
  estado.ms = Date.now() - inicio;
};

const erroresGraphQL = (): Array<{ message?: string; extensions?: Record<string, unknown> }> => {
  const errores = respuesta().data?.errors;
  return Array.isArray(errores) ? errores : [];
};

// Evidencia de cada escenario (pase o falle): último request y su response.
// El header Authorization se oculta para no filtrar el token en el reporte.
After(function () {
  if (!estado?.request) return;
  const headers = { ...estado.headers };
  if (headers.Authorization) headers.Authorization = 'Bearer ***';
  const res = estado.response;
  const cuerpo = JSON.stringify(res?.data, null, 2) ?? '';
  this.attach(
    [
      `REQUEST\n${estado.request.metodo} ${estado.request.url}`,
      `Headers: ${JSON.stringify(headers)}`,
      estado.request.body !== undefined ? `Body:\n${JSON.stringify(estado.request.body, null, 2)}` : '',
      `\nRESPONSE (${estado.ms} ms)\nStatus: ${res?.status} ${res?.statusText ?? ''}`,
      `Headers: ${JSON.stringify(res?.headers ?? {})}`,
      `Body:\n${cuerpo.length > 20000 ? cuerpo.slice(0, 20000) + '\n... (recortado)' : cuerpo}`,
    ].filter(Boolean).join('\n'),
    'text/plain'
  );
});

/* ---------- Given ---------- */

Given('el request usa el header {string} con valor {string}', (nombre: string, valor: string) => {
  estado.headers[nombre] = interpolar(valor);
});

Given('el request usa el token de autenticación', () => {
  const token = process.env.API_TOKEN;
  if (!token) throw new Error('Falta API_TOKEN en el .env de la raíz de k0lmenIA.');
  estado.headers.Authorization = `Bearer ${token}`;
});

Given('el request no envía token de autenticación', () => {
  delete estado.headers.Authorization;
});

Given('el endpoint GraphQL es {string}', (endpoint: string) => {
  estado.graphql.endpoint = endpoint;
});

Given('las variables GraphQL son:', (json: string) => {
  estado.graphql.variables = JSON.parse(interpolar(json));
});

/* ---------- When ---------- */

When('envío un {word} a {string}', async (metodo: string, endpoint: string) => {
  await enviar(metodo, endpoint);
});

When('envío un {word} a {string} con el body:', async (metodo: string, endpoint: string, body: string) => {
  await enviar(metodo, endpoint, body);
});

When('envío la consulta GraphQL:', async (query: string) => {
  await enviarGraphQL(query);
});

When('guardo el campo {string} de la respuesta como {string}', (campo: string, nombre: string) => {
  variables[nombre] = leerCampo(respuesta().data, campo);
});

/* ---------- Then ---------- */

Then('el status de la respuesta es {int}', (status: number) => {
  expect(respuesta().status, JSON.stringify(respuesta().data)?.slice(0, 500)).toBe(status);
});

Then('la respuesta contiene el campo {string}', (campo: string) => {
  expect(leerCampo(respuesta().data, campo)).not.toBeUndefined();
});

Then('la respuesta no contiene el campo {string}', (campo: string) => {
  expect(leerCampo(respuesta().data, campo)).toBeUndefined();
});

Then('el campo {string} de la respuesta es {string}', (campo: string, valor: string) => {
  expect(String(leerCampo(respuesta().data, campo))).toBe(interpolar(valor));
});

Then('el campo {string} de la respuesta es el número {float}', (campo: string, valor: number) => {
  expect(Number(leerCampo(respuesta().data, campo))).toBe(valor);
});

Then('el campo {string} de la respuesta es de tipo {string}', (campo: string, tipo: string) => {
  const v = leerCampo(respuesta().data, campo);
  const real = Array.isArray(v) ? 'array' : v === null ? 'null' : typeof v;
  expect(real).toBe(tipo);
});

Then('la respuesta es una lista', () => {
  expect(Array.isArray(respuesta().data)).toBe(true);
});

Then('la respuesta es una lista con al menos {int} elemento(s)', (min: number) => {
  expect(Array.isArray(respuesta().data)).toBe(true);
  expect(respuesta().data.length).toBeGreaterThanOrEqual(min);
});

Then('la respuesta tiene los campos:', (tabla: DataTable) => {
  // Tabla de una columna con las rutas de los campos obligatorios.
  for (const [campo] of tabla.raw()) {
    expect(leerCampo(respuesta().data, campo), `Falta el campo "${campo}"`).not.toBeUndefined();
  }
});

Then('el header {string} de la respuesta contiene {string}', (nombre: string, valor: string) => {
  expect(String(respuesta().headers[nombre.toLowerCase()] ?? '')).toContain(valor);
});

Then('la respuesta llega en menos de {int} ms', (max: number) => {
  expect(estado.ms ?? Infinity).toBeLessThan(max);
});

/* ---------- Then de GraphQL (los campos se leen dentro de "data") ---------- */

Then('la respuesta GraphQL no tiene errores', () => {
  expect(erroresGraphQL().map((e) => e.message), 'La respuesta GraphQL trae errores').toEqual([]);
});

Then('la respuesta GraphQL tiene un error con el mensaje {string}', (mensaje: string) => {
  const mensajes = erroresGraphQL().map((e) => String(e.message ?? ''));
  expect(mensajes.some((m) => m.includes(interpolar(mensaje))), `Errores: ${JSON.stringify(mensajes)}`).toBe(true);
});

Then('la respuesta GraphQL tiene un error con el código {string}', (codigo: string) => {
  const codigos = erroresGraphQL().map((e) => String(e.extensions?.code ?? ''));
  expect(codigos, `Errores: ${JSON.stringify(erroresGraphQL())}`).toContain(codigo);
});

Then('la respuesta GraphQL contiene el campo {string}', (campo: string) => {
  expect(leerCampo(respuesta().data?.data, campo), `Falta data.${campo}`).not.toBeUndefined();
});

Then('el campo GraphQL {string} es {string}', (campo: string, valor: string) => {
  expect(String(leerCampo(respuesta().data?.data, campo))).toBe(interpolar(valor));
});

Then('el campo GraphQL {string} es el número {float}', (campo: string, valor: number) => {
  expect(Number(leerCampo(respuesta().data?.data, campo))).toBe(valor);
});

Then('el campo GraphQL {string} es nulo', (campo: string) => {
  expect(leerCampo(respuesta().data?.data, campo)).toBeNull();
});

Then('el campo GraphQL {string} es una lista con al menos {int} elemento(s)', (campo: string, min: number) => {
  const v = leerCampo(respuesta().data?.data, campo);
  expect(Array.isArray(v), `data.${campo} no es una lista`).toBe(true);
  expect((v as unknown[]).length).toBeGreaterThanOrEqual(min);
});

When('guardo el campo GraphQL {string} como {string}', (campo: string, nombre: string) => {
  variables[nombre] = leerCampo(respuesta().data?.data, campo);
});
