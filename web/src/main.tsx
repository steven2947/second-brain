/** 产品浏览器入口；不读取服务端目录、数据库地址或模型凭据。 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { ProductApp } from './ProductApp';
import './styles/tokens.css';

const root = document.getElementById('root');
if (!root) throw new Error('缺少应用挂载节点');
ReactDOM.createRoot(root).render(<React.StrictMode><ProductApp /></React.StrictMode>);
