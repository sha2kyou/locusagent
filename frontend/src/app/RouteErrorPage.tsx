import { isRouteErrorResponse, useRouteError } from "react-router-dom";
import { AppErrorPage, formatThrownError } from "./AppErrorPage";

export function RouteErrorPage() {
  const error = useRouteError();
  let detail: string | undefined;

  if (isRouteErrorResponse(error)) {
    detail = error.statusText || String(error.status);
    if (typeof error.data === "string") detail = error.data;
  } else {
    detail = formatThrownError(error);
  }

  return <AppErrorPage detail={detail} />;
}
