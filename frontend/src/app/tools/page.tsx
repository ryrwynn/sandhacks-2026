import { redirect } from "next/navigation";

// The old tool picker now lives in the Tools menu of the top bar.
export default function Tools() {
  redirect("/");
}
