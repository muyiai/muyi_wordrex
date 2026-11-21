import { DATA_BASE } from '../config'
import { DataSource } from './data'
import { fileCache, wxFetcher } from './wx-io'

/** 全局唯一的数据源，各页面共用（同一本书只下载、解析一次）。 */
export const source = new DataSource(DATA_BASE, wxFetcher, fileCache)
