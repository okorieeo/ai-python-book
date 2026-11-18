"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiGet, type Params } from "@/lib/api";
import type {
  AdminUser,
  Me,
  Overview,
  Page,
  StatusCount,
  TopUser,
  UsageSeries,
} from "@/lib/types";

export const useMe = () =>
  useQuery({
    queryKey: ["me"],
    queryFn: () => apiGet<Me>("/me"),
    staleTime: 60_000,
  });

export const useOverview = () =>
  useQuery({
    queryKey: ["admin", "overview"],
    queryFn: () => apiGet<Overview>("/admin/overview"),
    refetchInterval: 60_000, // numbers on a wall screen stay fresh
  });

export const useUsageSeries = (days: number) =>
  useQuery({
    queryKey: ["admin", "usage", days],
    queryFn: () => apiGet<UsageSeries>("/admin/usage", { days }),
    placeholderData: keepPreviousData, // no flash when the range changes
  });

export const useTopUsers = (days: number) =>
  useQuery({
    queryKey: ["admin", "top-users", days],
    queryFn: () =>
      apiGet<TopUser[]>("/admin/usage/top-users", { days, limit: 5 }),
    placeholderData: keepPreviousData,
  });

export const useDocumentStatus = () =>
  useQuery({
    queryKey: ["admin", "documents-status"],
    queryFn: () => apiGet<StatusCount[]>("/admin/documents/status"),
  });

export const useAdminUsers = (params: Params) =>
  useQuery({
    queryKey: ["admin", "users", params], // every filter is part of the key
    queryFn: () => apiGet<Page<AdminUser>>("/admin/users", params),
    placeholderData: keepPreviousData, // keep the old rows while new ones load
  });
