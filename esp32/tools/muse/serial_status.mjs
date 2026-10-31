// Copyright (c) Meta Platforms, Inc. and affiliates. Apache-2.0.
// Preserve every JSON leaf, including false, 0, null and empty containers.
export function flattenStatus(value, path = '') {
  if (value !== null && typeof value === 'object' && Object.keys(value).length) {
    return Object.entries(value).flatMap(([key, child]) => flattenStatus(child,
      Array.isArray(value) ? `${path}[${key}]` : path ? `${path}.${key}` : key));
  }
  return [{ path, value }];
}
export function statusValue(value) {
  return typeof value === 'string' ? value : JSON.stringify(value);
}
