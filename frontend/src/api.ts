export let csrf = ''
export async function api(path: string, method = 'GET', body?: any): Promise<any> {
  const headers: Record<string,string> = {'X-CSRF-Token':csrf}
  if(body && !(body instanceof FormData)) headers['Content-Type']='application/json'
  const response = await fetch('/api/v1'+path,{method,headers,credentials:'same-origin',body:body instanceof FormData?body:body?JSON.stringify(body):undefined})
  const result = await response.json()
  if(!response.ok) { const error = new Error(result.error?.message || '请求失败') as any; error.status=response.status; error.details=result.error?.details; throw error }
  if(result.data?.csrf) csrf=result.data.csrf
  return result.data
}
